import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic

from matching import load_hostels, match_hostels

load_dotenv()

app = FastAPI()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Load hostels once at startup, not on every request
HOSTELS = load_hostels("hostels.json")


class SearchRequest(BaseModel):
    query: str


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

Respond ONLY with a JSON object, no explanation, no markdown, just raw JSON.
Use this exact structure:
{{
  "location": "city, region, or country name, or null if not mentioned",
  "budget_max": "maximum price per night as a number, or null if not mentioned",
  "budget_flexibility": "strict or approximate",
  "stay_duration_signal": "short_term or long_term or unknown",
  "party_preference": "avoid, prefer_quiet, neutral, prefer_social, or prefer_party",
  "vibe_tags": ["list", "of", "specific", "vibe", "keywords"],
  "traveler_profile": ["inferred", "traveler", "types", "based", "on", "context"]
}}
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    # Don't assume content[0] is the text block. Claude's response can
    # include multiple content blocks (e.g. a ThinkingBlock with internal
    # reasoning before the actual TextBlock, especially for queries with
    # more nuanced/mixed signals that trigger extended thinking). Search
    # for the block that actually has text rather than assuming position.
    raw = None
    for block in message.content:
        if getattr(block, "type", None) == "text":
            raw = block.text
            break

    if raw is None:
        raise ValueError(
            f"No text block found in Claude's response. Content block types received: "
            f"{[getattr(b, 'type', type(b).__name__) for b in message.content]}"
        )

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return json.loads(clean.strip())


@app.post("/search")
def search(request: SearchRequest):
    intent = parse_intent(request.query)
    outcome = match_hostels(intent, HOSTELS, top_n=10)

    return {
        "parsed_intent": intent,
        "total_matches": outcome["total_matches"],
        "results_returned": len(outcome["results"]),
        "results": outcome["results"],
    }
