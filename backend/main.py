import os
import json
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic

from matching import load_hostels, match_hostels
from semantic_similarity import load_hostel_embeddings

load_dotenv()

app = FastAPI()

# Allow the React dev server (different origin: localhost:5173 vs 127.0.0.1:8000)
# to call this API. Without this, the browser blocks every request before it
# even reaches FastAPI - this is a browser security rule (CORS), not optional.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Load hostels once at startup, not on every request
HOSTELS = load_hostels("hostels.json")
HOSTELS_BY_ID = {h["id"]: h for h in HOSTELS}

# Load precomputed vibe-profile embeddings once at startup too, for
# semantic matching (see matching.compute_semantic_entries). This is
# genuinely optional infrastructure: if hostel_embeddings.json hasn't
# been generated yet (or Voyage isn't reachable at request time later),
# search should still work — just without the semantic bonus score. Never
# let a missing/broken embeddings file take down the whole API.
try:
    HOSTEL_EMBEDDINGS = load_hostel_embeddings()
    print(f"Loaded {len(HOSTEL_EMBEDDINGS)} hostel vibe-profile embeddings for semantic matching.")
except Exception as e:
    HOSTEL_EMBEDDINGS = None
    print(f"WARNING: could not load hostel embeddings, semantic matching disabled: {e}")


def extract_text(message) -> str:
    """
    Don't assume content[0] is the text block. Claude's response can
    include multiple content blocks (e.g. a ThinkingBlock with internal
    reasoning before the actual TextBlock, especially for queries with
    more nuanced/mixed signals that trigger extended thinking). Search
    for the block that actually has text rather than assuming position.
    """
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError(
        f"No text block found in Claude's response. Content block types received: "
        f"{[getattr(b, 'type', type(b).__name__) for b in message.content]}"
    )


class SearchRequest(BaseModel):
    query: str


class BreakdownEntry(BaseModel):
    points: int
    reason: str


class ExplainRequest(BaseModel):
    intent: Dict[str, Any]
    hostel_id: int
    breakdown: List[BreakdownEntry]


@app.get("/")
def read_root():
    return {"message": "VibeMatch backend is alive"}


def parse_intent(query: str) -> dict:
    prompt = f"""You are an expert travel analyst who understands deep traveler psychology.
Extract structured information from this hostel search query.

Query: "{query}"

For traveler_profile, go beyond surface labels. Infer deeper traveler types based on context clues:
- Mentions metro/public transport access → likely "long_term_traveler", "daily_commuter"
- Mentions local market, cooking, fish bazaar, grocery shopping → likely "long_term_traveler", "self_cooker", "local_immersion_seeker"
- Mentions quiet after certain hour, early morning → "peace_lover", "early_riser"
- Mentions budget, cheap, under $X → "budget_conscious"
- Mentions wifi, work, laptop → "digital_nomad"
- Mentions party, nightlife, social → "party_traveler"
- Mentions culture, museum, history → "culture_seeker"
- Mentions hiking, trekking, adventure → "adventure_traveler"
- Short stay signals (1-2 nights, transit) → "transit_traveler"

For stay_duration_signal, combine weak signals rather than requiring an explicit mention:
- If 2 or more long-stay indicators are present together, set stay_duration_signal to "long_term"
- If explicit short stay language is used, set stay_duration_signal to "short_term"
- Only use "unknown" if there are truly no contextual clues either way

For budget_flexibility, distinguish two different kinds of budget language:
- "strict" — the traveler named a hard ceiling: "under $15", "no more than $10", "max $20", "below $8"
- "approximate" — the traveler named a rough target, not a hard cutoff: "around $10", "about $15", "roughly $20", "~$12"
- Default to "strict" if budget_max is null (no budget mentioned at all) or if the wording is ambiguous — approximate should only be used when the language clearly signals flexibility.

For party_preference, classify where the traveler sits on a party/social spectrum, even if not stated in those exact words. Pay attention to INTENSITY, not just direction:
- "avoid" — a strong, explicit rejection of party atmosphere: "not a party place", "no party scene", "definitely not a party hostel"
- "prefer_quiet" — a milder preference for lower-key over lively, without fully rejecting all social energy: "not much a party place", "priority is calmness", "somewhere chill", "low-key would be nice"
- "neutral" — no signal either way about party/social atmosphere
- "prefer_social" — wants a social, lively atmosphere without necessarily being a full-on party hostel: "sociable", "like meeting people", "good vibe in the evenings"
- "prefer_party" — explicitly wants a party hostel, nightlife, loud social scene: "party hostel", "nightlife", "want to rage"
- Default to "neutral" if there's no clear signal either way.
- ALWAYS fill this field the same way regardless of whether daytime_vibe_preference/evening_vibe_preference below are also set — it's the fallback the matching engine uses for any query that isn't genuinely time-varying.

For daytime_vibe_preference and evening_vibe_preference (EXPERIMENTAL, see DECISIONS_LOG.md — hostel-side day/night data doesn't exist yet, these are currently only exercised against a synthetic test fixture): only set these two fields — each "quiet", "social", or null — when the query CLEARLY expresses a DIFFERENT preference for daytime vs. evening within the same stay. This is a genuinely different signal than party_preference, which describes one overall vibe.
- Example that SHOULD set both: "somewhere I can focus during the day but still meet people over dinner" → daytime_vibe_preference: "quiet", evening_vibe_preference: "social".
- Example that SHOULD set both: "quiet mornings, social nights" → daytime_vibe_preference: "quiet", evening_vibe_preference: "social".
- Example that should NOT set either (leave both null): "chill hostel, not too party" — this is one overall preference, not a day/night split; party_preference alone covers it.
- Example that should NOT set either: "party hostel with nightlife" — also one overall preference.
- Default: leave BOTH null unless the query genuinely names two different times of day with two different vibes.

Respond ONLY with a JSON object, no explanation, no markdown, just raw JSON.
Use this exact structure:
{{
  "location": "city, region, or country name, or null if not mentioned",
  "budget_max": "maximum price per night as a number, or null if not mentioned",
  "budget_flexibility": "strict or approximate",
  "stay_duration_signal": "short_term or long_term or unknown",
  "party_preference": "avoid, prefer_quiet, neutral, prefer_social, or prefer_party",
  "daytime_vibe_preference": "quiet, social, or null",
  "evening_vibe_preference": "quiet, social, or null",
  "vibe_tags": ["list", "of", "specific", "vibe", "keywords"],
  "traveler_profile": ["inferred", "traveler", "types", "based", "on", "context"]
}}
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = extract_text(message)
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return json.loads(clean.strip())


def generate_explanation(intent: dict, hostel: dict, breakdown: list) -> dict:
    reasons_text = "\n".join(f"- {b['reason']}" for b in breakdown)

    flagged_issues = hostel.get("flagged_issues", [])
    flagged_text = ""
    if flagged_issues:
        flagged_lines = "\n".join(
            f"- {f['issue']} (frequency: {f.get('frequency', 'unknown')}, severity: {f.get('severity', 'unknown')})"
            for f in flagged_issues
        )
        flagged_text = f"""

Known flagged issues from past guest reviews:
{flagged_lines}

Include EVERY flagged issue that's genuinely relevant to this traveler's specific search — not
just one. If the traveler asked about safety and there's a safety-related flag, that's relevant;
a flagged issue about something the traveler didn't ask about (e.g. unrelated to their search)
can be left out. When multiple issues are included, order them most severe first. Weight tone by
SEVERITY, not just frequency — a "serious" issue must be treated with real weight regardless of
how rare it is; a "minor" issue can be phrased lightly."""

    prompt = f"""You are a fast, honest travel assistant. A backpacker is scanning search results
quickly — often on their phone, sometimes standing on a street with a bag on their back, not
sitting down to read a paragraph. Respond with SHORT, SCANNABLE fragments, not full sentences
joined into prose.

Traveler's search intent:
{json.dumps(intent, indent=2)}

Hostel: {hostel.get('name')} in {hostel.get('city')}, {hostel.get('country')}
Exclusive features: {', '.join(hostel.get('exclusive_features', [])) or 'none listed'}
Vibe tags: {', '.join(hostel.get('vibe_tags', [])) or 'none listed'}
Reviews summary: {hostel.get('reviews_summary', 'not available')}

Why the matching engine scored this hostel for this search:
{reasons_text}
{flagged_text}

Respond ONLY with a JSON object, no markdown, no explanation outside the JSON. Use this exact
structure:
{{
  "verdict": "one short, honest phrase (under 10 words) judging overall fit — can be lukewarm or mixed if that's accurate, never just positive spin for its own sake",
  "highlights": ["1 to 4 short fragments, each a specific concrete reason this hostel fits — NOT full sentences"],
  "heads_ups": ["0 or more short fragments for genuine caveats or flagged issues relevant to THIS search — return an empty list if there's nothing worth flagging, never pad this to hit a count"]
}}

Each highlight and heads_up must be a short scannable fragment (roughly 5-12 words), written like
a label a tired person can read in half a second — not a grammatically complete sentence."""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = extract_text(message)
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return json.loads(clean.strip())


@app.post("/search")
def search(request: SearchRequest):
    intent = parse_intent(request.query)
    outcome = match_hostels(
        intent, HOSTELS, top_n=10,
        raw_query=request.query,
        hostel_embeddings=HOSTEL_EMBEDDINGS,
    )

    return {
        "parsed_intent": intent,
        "total_matches": outcome["total_matches"],
        "results_returned": len(outcome["results"]),
        "results": outcome["results"],
    }


@app.post("/explain")
def explain(request: ExplainRequest):
    hostel = HOSTELS_BY_ID.get(request.hostel_id)
    if hostel is None:
        raise HTTPException(status_code=404, detail="Hostel not found")

    breakdown = [{"points": b.points, "reason": b.reason} for b in request.breakdown]
    result = generate_explanation(request.intent, hostel, breakdown)

    # result is already {"verdict": ..., "highlights": [...], "heads_ups": [...]}
    return result
