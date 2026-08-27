"""
normalize_nearby_and_boutique.py

Two independent, cheap normalization passes using ONLY existing data
(no new web research) — same pattern as reclassify_party_level.py and
normalize_views.py.

1. location.nearby: currently a flat list of strings with distance/time
   informally embedded ("Palolem Beach (13 min walk)", "Odayam Beach
   (80m)") for 118/228 hostels, with no type classification, and never
   referenced anywhere in matching.py. Restructured into
   [{"name": str, "type": "cafe"|"nature"|"landmark"|"nightlife"|"beach"|
   "viewpoint"|"market"|"other", "distance_km": float|null, "walkable":
   bool}] by parsing the existing embedded distance text and classifying
   each place's type. The other 110 hostels with no `nearby` data at all
   are left untouched here — that needs genuine new research, tracked as
   the separate, larger data-enrichment pass.

2. is_boutique_style: a new field, classified from existing
   accommodation_type/vibe_tags/facilities/exclusive_features/price_range
   — "boutique" is a style descriptor that cuts across accommodation_type
   (a boutique hostel is still fundamentally a hostel) rather than being
   its own category, so this is a separate boolean rather than a new
   accommodation_type value.

Resumable: writes progress after every hostel.
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

PLACE_TYPE_VOCAB = ["cafe", "nature", "landmark", "nightlife", "beach", "viewpoint", "market", "other"]

SYSTEM_PROMPT = f"""You do two things given a hostel's existing data, using ONLY the data given:

1. Parse the `raw_nearby` list (free-text place names, often with informal distance/time embedded,
   e.g. "Palolem Beach (13 min walk)", "Odayam Beach (80m)") into a structured list. For each entry:
   - "name": the place name, with any embedded distance/time text removed
   - "type": one of {PLACE_TYPE_VOCAB} — best fit based on the name
   - "distance_km": a numeric estimate in km if the source gives distance or walking time (assume
     ~4.5 km/h average walking pace to convert "13 min walk" -> ~1.0 km; "80m" -> 0.08;
     "400yd" -> ~0.37), or null if no distance/time signal is present at all — do not guess a
     number with zero basis.
   - "walkable": true if distance_km <= 3.0 (a reasonable single-trip walk) or if the source
     text says "walk"/"min walk" explicitly, false if distance_km > 3.0, null if unknown.

2. Classify "is_boutique_style": true if the accommodation_type, vibe_tags, facilities, and
   exclusive_features data clearly signal a boutique/design-focused/upscale-styled property
   (curated interior design, art focus, small guest count marketed as a feature, "boutique" in
   vibe_tags or name, etc.) — false if it reads as a standard/budget/functional hostel — do not
   guess if there's no real signal either way, use false as the default (boutique is the
   exception, not the default).

Output ONLY valid JSON: {{"nearby": [...], "is_boutique_style": true|false}}
No markdown fences, no other text."""


def build_context(h: dict) -> dict:
    return {
        "name": h.get("name"),
        "raw_nearby": h.get("location", {}).get("nearby"),
        "accommodation_type": h.get("accommodation_type"),
        "vibe_tags": h.get("vibe_tags"),
        "facilities": h.get("facilities"),
        "exclusive_features": h.get("exclusive_features"),
        "price_range_usd": h.get("price_range_usd"),
    }


def extract_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("No text block in response")


def process(h: dict) -> dict:
    context = build_context(h)
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
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

    print(f"Processing all {len(hostels)} hostels for is_boutique_style; "
          f"restructuring location.nearby where it already exists.\n")

    boutique_count = 0
    nearby_restructured_count = 0

    for i, h in enumerate(hostels, 1):
        try:
            result = process(h)

            h["is_boutique_style"] = result["is_boutique_style"]
            if result["is_boutique_style"]:
                boutique_count += 1

            if h.get("location", {}).get("nearby"):
                h["location"]["nearby_raw_text"] = h["location"]["nearby"]  # preserve original
                h["location"]["nearby"] = result["nearby"]
                nearby_restructured_count += 1

            marker = " [BOUTIQUE]" if result["is_boutique_style"] else ""
            print(f"[{i}/{len(hostels)}] {h['name']!r}{marker} - nearby entries: {len(result['nearby'])}")

            with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
                json.dump(hostels, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"[{i}/{len(hostels)}] {h.get('name')} FAILED: {e}")
            time.sleep(2)
            continue

    print(f"\nDone. Boutique-style hostels: {boutique_count}")
    print(f"location.nearby restructured for: {nearby_restructured_count} hostels")


if __name__ == "__main__":
    main()
