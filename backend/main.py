import os
import json
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic

from matching import load_hostels, match_hostels

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

    raw = extract_text(message)
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return json.loads(clean.strip())


def generate_explanation(intent: dict, hostel: dict, breakdown: list) -> str:
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

Mention the ONE most relevant flagged issue for this traveler's specific search, briefly and
honestly. IMPORTANT: weight your tone by SEVERITY, not just frequency. A "minor" issue (e.g.
occasional cleanliness annoyance) can be mentioned lightly, softened by its rarity. A "serious"
issue (e.g. a genuine safety concern) must be treated with real weight and clear caution
REGARDLESS of how rare/isolated it is — do not minimize a serious issue just because it's a
single report. Frequency tells you how often something happens; severity tells you how much it
matters if it does. Never let "isolated" language soften a serious issue into sounding like a
minor inconvenience."""

    prompt = f"""You are a friendly, well-traveled assistant explaining to a traveler why a specific
hostel was recommended for their search. Be warm and conversational, like a friend giving a
genuine recommendation — not a robotic restatement of a scoring system.

Traveler's search intent:
{json.dumps(intent, indent=2)}

Hostel: {hostel.get('name')} in {hostel.get('city')}, {hostel.get('country')}
Exclusive features: {', '.join(hostel.get('exclusive_features', [])) or 'none listed'}
Vibe tags: {', '.join(hostel.get('vibe_tags', [])) or 'none listed'}
Reviews summary: {hostel.get('reviews_summary', 'not available')}

Why the matching engine scored this hostel well for this search:
{reasons_text}
{flagged_text}

Write a warm, natural 2-4 sentence explanation of why this hostel is a good match for what the
traveler is looking for. Synthesize the reasons above into a narrative — don't just list them
mechanically. Plain text only, no markdown formatting."""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    return extract_text(message).strip()


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


@app.post("/explain")
def explain(request: ExplainRequest):
    hostel = HOSTELS_BY_ID.get(request.hostel_id)
    if hostel is None:
        raise HTTPException(status_code=404, detail="Hostel not found")

    breakdown = [{"points": b.points, "reason": b.reason} for b in request.breakdown]
    explanation = generate_explanation(request.intent, hostel, breakdown)

    return {"explanation": explanation}
