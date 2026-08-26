"""
reclassify_party_level.py

Adds a genuine "none" tier below "low" on the party_level scale, and
reclassifies every currently-"low" hostel into either "none" or "low"
using EXISTING data already gathered for each hostel (reviews_summary,
social_vibe.social_activities, flagged_issues, vibe_profile) — no new web
research, since the signal needed to distinguish "genuinely silent" from
"a little weekend activity" is very likely already present in what we
already collected.

Why this distinction matters (per direct product discussion): "low" was
being used to mean two different things — a hostel with truly no
social/party element, and a hostel with occasional light activity. A
traveler who says "avoid party" wants the first; a traveler who says "no
party preferred" is fine with a little of the second. Conflating them
meant the scoring formula couldn't express that difference. See
DECISIONS_LOG.md for the full writeup.

Classification is done by Claude, given ONLY each hostel's own existing
fields (never invents new facts), and returns a confidence level.
Low-confidence classifications are flagged for manual review rather than
silently applied — same "don't fabricate, disclose uncertainty" principle
used throughout this project's data (source_note, research_depth, etc).

Resumable: writes progress to hostels.json after every hostel.
"""

import os
import json
import time
from dotenv import load_dotenv
import anthropic

load_dotenv()

HOSTELS_PATH = os.path.join(os.path.dirname(__file__), "hostels.json")
MODEL = "claude-haiku-4-5"

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You classify a hostel's true social/party level using ONLY the data given to you.

Two categories to choose between:
- "none": the hostel is genuinely quiet/silent with essentially no social or party element —
  explicitly described as peaceful, meditation-focused, a B&B-style retreat, no bar/no organized
  social events, guests there specifically to avoid noise/socializing.
- "low": the hostel has SOME light social activity — occasional gatherings, a small common area
  where people chat, maybe weekend get-togethers — even if it's clearly not a party hostel. This
  is the default if you don't see a clear, explicit signal for "none".

Rules:
- Base your answer ONLY on the data given. Do not invent or assume facts not present.
- Default to "low" unless there's a genuinely clear signal of "none" — being conservative here
  matters, since misclassifying a slightly-social hostel as "none" would mislead a traveler who
  explicitly wants zero social element.
- Also return a confidence: "high" (clear, explicit signal either way), "medium" (reasonable
  inference but not explicit), or "low" (genuinely ambiguous, a human should double check).
- Output ONLY valid JSON: {"party_level": "none" | "low", "confidence": "high" | "medium" | "low", "reasoning": "one sentence"}
No markdown fences, no other text."""


def build_context(h: dict) -> dict:
    return {
        "name": h.get("name"),
        "vibe_tags": h.get("vibe_tags"),
        "reviews_summary": h.get("reviews_summary"),
        "social_vibe": h.get("social_vibe"),
        "flagged_issues": h.get("flagged_issues"),
        "vibe_profile": h.get("vibe_profile"),
    }


def extract_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("No text block in response")


def classify(h: dict) -> dict:
    context = build_context(h)
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(context, indent=2, ensure_ascii=False)}],
    )
    text = extract_text(response).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        if text.strip().startswith("json"):
            text = text.strip()[4:]
    return json.loads(text.strip())


def main():
    with open(HOSTELS_PATH, "r", encoding="utf-8") as f:
        hostels = json.load(f)

    low_hostels = [h for h in hostels if h.get("social_vibe", {}).get("party_level") == "low"]
    print(f"Found {len(low_hostels)} hostels currently tagged 'low' to reclassify.\n")

    reclassified_to_none = []
    kept_low = []
    flagged_for_review = []

    for i, h in enumerate(low_hostels, 1):
        try:
            result = classify(h)
            new_level = result["party_level"]
            confidence = result["confidence"]
            reasoning = result["reasoning"]

            h["social_vibe"]["party_level"] = new_level
            # Record the reclassification for transparency/audit, same spirit as source_note.
            h["social_vibe"]["party_level_reclassification_note"] = (
                f"Reclassified from 'low' to '{new_level}' (confidence: {confidence}): {reasoning}"
            )

            print(f"[{i}/{len(low_hostels)}] {h['name']!r} -> {new_level} ({confidence}): {reasoning}")

            if new_level == "none":
                reclassified_to_none.append(h["name"])
            else:
                kept_low.append(h["name"])
            if confidence == "low":
                flagged_for_review.append(h["name"])

            with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
                json.dump(hostels, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"[{i}/{len(low_hostels)}] {h.get('name')} FAILED: {e}")
            time.sleep(2)
            continue

    print(f"\nDone. Reclassified to 'none': {len(reclassified_to_none)}")
    for n in reclassified_to_none:
        print("  -", n)
    print(f"\nKept as 'low': {len(kept_low)}")
    print(f"\nFlagged for manual review (low confidence): {len(flagged_for_review)}")
    for n in flagged_for_review:
        print("  -", n)


if __name__ == "__main__":
    main()
