import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = FastAPI()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class SearchRequest(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {"message": "VibeMatch backend is alive"}

@app.post("/search")
def parse_intent(request: SearchRequest):
    prompt = f"""You are an expert travel analyst who understands deep traveler psychology.
Extract structured information from this hostel search query.

Query: "{request.query}"

For traveler_profile, go beyond surface labels. Infer deeper traveler types based on context clues:
- Mentions metro/public transport access → likely "long_term_traveler", "daily_commuter" (daily commuting suggests extended stay, not a 1-2 night visit)
- Mentions local market, cooking, fish bazaar, grocery shopping → likely "long_term_traveler", "self_cooker", "local_immersion_seeker" (cooking and market visits suggest settling in, not quick transit)
- Mentions quiet after certain hour, early morning → "peace_lover", "early_riser"
- Mentions budget, cheap, under $X → "budget_conscious"
- Mentions wifi, work, laptop → "digital_nomad"
- Mentions party, nightlife, social → "party_traveler"
- Mentions culture, museum, history → "culture_seeker"
- Mentions hiking, trekking, adventure → "adventure_traveler"
- Short stay signals (1-2 nights, transit, layover) → "transit_traveler"

For stay_duration_signal, combine weak signals rather than requiring an explicit mention:
- If 2 or more long-stay indicators are present together (e.g. metro access + cooking interest + neighborhood familiarity), set stay_duration_signal to "long_term"
- If explicit short stay language is used (1-2 nights, layover, transit), set stay_duration_signal to "short_term"
- Only use "unknown" if there are truly no contextual clues either way

Respond ONLY with a JSON object, no explanation, no markdown, just raw JSON.
Use this exact structure:
{{
  "location": "city or country name, or null if not mentioned",
  "budget_max": "maximum price per night as a number, or null if not mentioned",
  "stay_duration_signal": "short_term or long_term or unknown",
  "vibe_tags": ["list", "of", "specific", "vibe", "keywords"],
  "traveler_profile": ["inferred", "traveler", "types", "based", "on", "context"]
}}
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    print("RAW RESPONSE:", raw)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    parsed = json.loads(clean.strip())
    return parsed