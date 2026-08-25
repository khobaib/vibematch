"""
semantic_similarity.py

Loads the precomputed hostel embeddings (hostel_embeddings.json, built by
embed_vibe_profiles.py) and provides a lookup: given a free-text query,
return a cosine-similarity score against every hostel's vibe_profile
embedding.

This module is intentionally standalone/testable without FastAPI or the
matching engine, so it can be validated on its own before Task #5 wires it
into score_hostel() as a new, auditable breakdown line.

Query vs. document embedding: Voyage's models are trained asymmetrically -
content you're indexing should be embedded as "document" (done once, at
data-prep time, in embed_vibe_profiles.py), while text a user types to
search should be embedded as "query" (done here, at request time). Using
the matching input_type on each side is what Voyage's retrieval quality
tuning assumes; mixing them up would silently degrade relevance without
throwing any error.
"""

import os
import json
import math
from dotenv import load_dotenv
import voyageai

load_dotenv()

EMBEDDINGS_PATH = os.path.join(os.path.dirname(__file__), "hostel_embeddings.json")
MODEL = "voyage-4"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return _client


def load_hostel_embeddings(path: str = EMBEDDINGS_PATH) -> dict:
    """
    Returns {hostel_id (int): embedding (list[float])}.
    Raises FileNotFoundError with a clear message if embeddings haven't
    been generated yet - this should fail loudly, not silently degrade
    the matching engine.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run embed_vibe_profiles.py first to generate hostel embeddings."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stored_model = data.get("model")
    if stored_model != MODEL:
        raise ValueError(
            f"hostel_embeddings.json was built with model {stored_model!r}, "
            f"but semantic_similarity.py expects {MODEL!r}. Re-run embed_vibe_profiles.py "
            f"or update MODEL here to match."
        )

    return {int(hid): vec for hid, vec in data["embeddings"].items()}


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_query(query_text: str) -> list:
    """
    Embeds free-text query using input_type="query" (asymmetric retrieval -
    see module docstring). Makes a live Voyage API call, so this is only
    called at request time for the user's actual search text, never in a
    loop over hostels.
    """
    client = _get_client()
    result = client.embed([query_text], model=MODEL, input_type="query")
    return result.embeddings[0]


def semantic_scores(query_text: str, hostel_embeddings: dict = None) -> dict:
    """
    Returns {hostel_id: cosine_similarity} for every hostel, given a
    free-text query describing the desired vibe. Cosine similarity for
    Voyage embeddings typically ranges roughly 0.0-1.0 for related text,
    with most real-world pairs falling somewhere in the 0.3-0.8 band -
    there's no fixed "0 to 1 evenly spread" guarantee, so callers should
    look at *relative* ranking/spread rather than assuming an absolute
    scale when converting this into match-engine points (Task #5).
    """
    if hostel_embeddings is None:
        hostel_embeddings = load_hostel_embeddings()

    query_vec = embed_query(query_text)

    return {
        hostel_id: cosine_similarity(query_vec, hostel_vec)
        for hostel_id, hostel_vec in hostel_embeddings.items()
    }


def top_matches(query_text: str, hostels_by_id: dict, hostel_embeddings: dict = None, top_n: int = 10):
    """
    Convenience helper for manual testing: returns [(hostel_name, score), ...]
    sorted descending, for eyeballing whether semantic ranking makes sense.
    """
    scores = semantic_scores(query_text, hostel_embeddings)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [(hostels_by_id[hid]["name"], round(score, 4)) for hid, score in ranked if hid in hostels_by_id]
