"""
generate_vibe_profiles.py

Generates a short, natural-language "vibe profile" paragraph for every
hostel in hostels.json, using Claude Haiku 4.5. This paragraph is written
specifically to be embedded (via Voyage AI) for semantic vibe matching -
it's meant to read naturally and capture *how* a hostel's traits relate to
each other (not just list tags), since that's what makes embeddings useful
over the raw structured fields we already match on exactly.

Design notes:
- Idempotent / resumable: writes progress to hostels.json after every
  hostel, and skips any hostel that already has a "vibe_profile" field
  unless --force is passed. Safe to re-run if interrupted.
- Uses only the fields most relevant to "vibe" (not the full room-type /
  pricing structure) to keep input tokens low and the model focused.
- Every profile is written in the same consistent register (present tense,
  descriptive, no marketing fluff, no invented facts) so embeddings are
  comparable across hostels.
"""

import os
import json
import time
import argparse
from dotenv import load_dotenv
import anthropic

load_dotenv()

HOSTELS_PATH = os.path.join(os.path.dirname(__file__), "hostels.json")
MODEL = "claude-haiku-4-5"

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You write short "vibe profiles" for backpacker hostels, to be used as \
input for semantic embedding and similarity search. Given structured data about a hostel, \
write a natural-language paragraph (3-5 sentences, 60-110 words) describing the *feel* \
and *experience* of staying there - who it suits, what the social/sleep/work atmosphere \
is like, and any standout traits.

Rules:
- Base the profile ONLY on the data given. Never invent amenities, ratings, or facts not present.
- If a field is null/missing, simply don't mention that aspect - don't guess or hedge about it.
- Write in flowing prose, not a list of tags. Avoid marketing language ("amazing", "perfect", \
"must-visit") - be descriptive and neutral, like a well-informed friend describing the place.
- If flagged_issues are present, incorporate the general character of the concern naturally \
(e.g. "some guests have reported dampness issues") without being alarmist - match the severity.
- Do not mention price, location/city name, or exact review scores - those are handled by other \
parts of the matching system. Focus purely on atmosphere, social scene, comfort, and who it fits.
- Output ONLY the paragraph. No preamble, no quotes, no headers."""


def build_hostel_context(h: dict) -> dict:
    """Extract only the vibe-relevant fields, to keep the prompt focused and cheap."""
    return {
        "name": h.get("name"),
        "accommodation_type": h.get("accommodation_type"),
        "vibe_tags": h.get("vibe_tags"),
        "social_vibe": h.get("social_vibe"),
        "reviews_summary": h.get("reviews_summary"),
        "facilities": h.get("facilities"),
        "exclusive_features": h.get("exclusive_features"),
        "cleanliness_signal": h.get("cleanliness_signal"),
        "sleep_comfort": h.get("sleep_comfort"),
        "staff": h.get("staff"),
        "kitchen_food": h.get("kitchen_food"),
        "flagged_issues": h.get("flagged_issues"),
        "views": h.get("views"),
    }


def extract_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("No text block found in Claude response")


def generate_profile(h: dict) -> str:
    context = build_hostel_context(h)
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Hostel data:\n{json.dumps(context, indent=2, ensure_ascii=False)}",
            }
        ],
    )
    return extract_text(response).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Regenerate even if vibe_profile already exists")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N hostels missing a profile (for testing)")
    args = parser.parse_args()

    with open(HOSTELS_PATH, "r", encoding="utf-8") as f:
        hostels = json.load(f)

    todo = [h for h in hostels if args.force or not h.get("vibe_profile")]
    if args.limit:
        todo = todo[: args.limit]

    print(f"Total hostels: {len(hostels)}")
    print(f"To process: {len(todo)}")

    total_input_tokens = 0
    total_output_tokens = 0

    for i, h in enumerate(todo, 1):
        try:
            context = build_hostel_context(h)
            response = client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Hostel data:\n{json.dumps(context, indent=2, ensure_ascii=False)}",
                    }
                ],
            )
            profile_text = extract_text(response).strip()
            h["vibe_profile"] = profile_text

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            print(f"[{i}/{len(todo)}] id={h['id']} {h['name']!r} -> {len(profile_text)} chars")

            # Save progress after every hostel so a crash/interrupt loses at most one call.
            with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
                json.dump(hostels, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"[{i}/{len(todo)}] id={h.get('id')} FAILED: {e}")
            time.sleep(2)
            continue

    cost = (total_input_tokens / 1_000_000) * 1.0 + (total_output_tokens / 1_000_000) * 5.0
    print("\nDone.")
    print(f"Total input tokens:  {total_input_tokens:,}")
    print(f"Total output tokens: {total_output_tokens:,}")
    print(f"Estimated cost: ${cost:.4f}")


if __name__ == "__main__":
    main()
