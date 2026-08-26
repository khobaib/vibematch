"""
normalize_views.py

The `views` field (has_view, view_type, view_from) exists in hostels.json
for 62 hostels, but view_type/view_from were originally filled in as
free-text with no controlled vocabulary — inconsistent formatting
("rooftop terrace" vs "rooftop_terrace"), multi-concept strings joined
together ("balcony views, cliff-adjacent"), and values that mix view_from
info into view_type ("city view balcony in some rooms"). This makes
reliable matching impossible even once the field is wired into scoring.

This script re-reads each has_view=true hostel's EXISTING free-text
view_type/view_from (plus vibe_profile/reviews_summary for extra context —
no new web research) and normalizes both into fixed controlled vocabularies,
as LISTS (a hostel can genuinely have more than one view type, or be
visible from more than one place — the old single-string format couldn't
express that without hacky "_and_" concatenation).

Resumable: writes progress after every hostel. Only touches hostels where
has_view is true — hostels without a view are untouched.
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

# Expanded after the first real run surfaced 3 legitimate gaps (park,
# volcano, courtyard) that weren't in the original list — the model
# correctly identified them as clean, single-concept categories rather
# than forcing them into "other" and losing real signal. Kept here so a
# future re-run of this script (e.g. after new hostels are added) uses
# the same, now-validated vocabulary.
VIEW_TYPE_VOCAB = [
    "ocean", "mountain", "lake", "river", "valley", "city", "garden",
    "jungle", "pool", "temple", "cliff", "rooftop_skyline", "countryside",
    "rice_paddy", "desert", "park", "volcano", "other",
]
VIEW_FROM_VOCAB = [
    "room", "rooftop", "common_area", "terrace", "balcony",
    "property_grounds", "restaurant", "pool_area", "cabana", "courtyard", "other",
]

SYSTEM_PROMPT = f"""You normalize free-text hostel view descriptions into fixed controlled
vocabularies, using ONLY the data given.

view_type must be a list using ONLY these values: {VIEW_TYPE_VOCAB}
view_from must be a list using ONLY these values: {VIEW_FROM_VOCAB}

Rules:
- Base your answer ONLY on the existing free-text view_type/view_from and any other context given.
  Do not invent details not implied by the source text.
- A hostel can genuinely have more than one view type (e.g. "garden and temple views" ->
  ["garden", "temple"]) or be visible from more than one place (e.g. "rooftop_and_room" ->
  ["rooftop", "room"]) — return every value that's genuinely supported by the source text, not
  just one.
- If the source text mentions a view/location concept not covered by the vocab, use "other" and
  do not fabricate a new category.
- If the original view_from/view_type is null/missing despite has_view being true, use your best
  judgment from the other context fields (vibe_profile, reviews_summary) — but if there's truly no
  signal, return an empty list rather than guessing.
- Output ONLY valid JSON: {{"view_type": [...], "view_from": [...]}}
No markdown fences, no other text."""


def build_context(h: dict) -> dict:
    views = h.get("views", {})
    return {
        "name": h.get("name"),
        "original_view_type": views.get("view_type"),
        "original_view_from": views.get("view_from"),
        "vibe_profile": h.get("vibe_profile"),
        "reviews_summary": h.get("reviews_summary"),
    }


def extract_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("No text block in response")


def normalize(h: dict) -> dict:
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

    to_process = [h for h in hostels if h.get("views", {}).get("has_view") is True]
    print(f"Found {len(to_process)} hostels with has_view=true to normalize.\n")

    for i, h in enumerate(to_process, 1):
        try:
            result = normalize(h)
            old_type = h["views"].get("view_type")
            old_from = h["views"].get("view_from")

            h["views"]["view_type"] = result["view_type"]
            h["views"]["view_from"] = result["view_from"]
            h["views"]["original_free_text"] = {
                "view_type": old_type,
                "view_from": old_from,
            }

            print(f"[{i}/{len(to_process)}] {h['name']!r}")
            print(f"    view_type: {old_type!r} -> {result['view_type']}")
            print(f"    view_from: {old_from!r} -> {result['view_from']}")

            with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
                json.dump(hostels, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"[{i}/{len(to_process)}] {h.get('name')} FAILED: {e}")
            time.sleep(2)
            continue

    print("\nDone.")


if __name__ == "__main__":
    main()
