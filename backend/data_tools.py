"""
data_tools.py

Single toolkit for all hostel-data enrichment/normalization work. Replaces
the earlier one-off scripts (normalize_views.py, reclassify_party_level.py,
normalize_nearby_and_boutique.py, merge_pilot_research.py) — those files
each did real, useful work and are why hostels.json looks the way it does
today, but writing a brand new .py file for every future field/pass was
never going to scale as the schema keeps growing. This file replaces them
with two reusable, parameterized operations instead of one script per task.

WHY TWO OPERATIONS, NOT ONE:
These earlier scripts were actually doing two structurally different jobs
that happened to look similar:

1. NORMALIZE — re-read a hostel's OWN existing fields via Claude Haiku and
   restructure/reclassify them (no new facts, no internet access). This is
   what normalize_views.py, reclassify_party_level.py, and
   normalize_nearby_and_boutique.py all did. Now expressed as entries in
   the NORMALIZE_TASKS registry below — adding a new normalization task
   (e.g. a future "reclassify curfew tone" pass) means adding one entry to
   that dict, not a new file.

2. MERGE — apply NEW research gathered elsewhere (e.g. Agent subagents
   doing real WebSearch/WebFetch) into hostels.json. This is what
   merge_pilot_research.py did, except that script hardcoded the Thailand+
   India results directly in Python source, which meant "the next batch"
   would have needed yet another near-duplicate file. Now the research
   results live as plain JSON data files under research_batches/ (see
   research_batches/thailand_india_2026_08.json for the pilot's actual
   data), and this file's `merge` command applies any such file generically
   via MERGE_FIELD_MAP. A brand new field just needs one line added to that
   map — not a new script.

USAGE:
    python data_tools.py normalize views
    python data_tools.py normalize party_level
    python data_tools.py normalize boutique_nearby
    python data_tools.py merge research_batches/thailand_india_2026_08.json --batch-name thailand_india_2026_08

    # for the NEXT country batch, once an Agent-subagent research pass produces
    # a results file (same shape as thailand_india_2026_08.json — a JSON list
    # of {"id": int, ...fields..., "sources": [...]}), just:
    python data_tools.py merge research_batches/<new_batch_name>.json --batch-name <new_batch_name>

Both operations are resumable/idempotent in the same spirit as the original
scripts: `normalize` writes hostels.json after every hostel, `merge` writes
once at the end (it's not making live API calls, so there's nothing to lose
by not saving incrementally).
"""

import os
import sys
import json
import time
import argparse
from dotenv import load_dotenv
import anthropic

load_dotenv()

HOSTELS_PATH = os.path.join(os.path.dirname(__file__), "hostels.json")
MODEL = "claude-haiku-4-5"

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def load_hostels():
    with open(HOSTELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_hostels(hostels):
    with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
        json.dump(hostels, f, indent=2, ensure_ascii=False)


def extract_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("No text block in response")


def call_haiku(system_prompt: str, context: dict, max_tokens: int = 500) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
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


# ---------------------------------------------------------------------------
# NORMALIZE — re-read existing data only, no new research. See module
# docstring. Each task defines: which hostels to touch (filter), what to
# tell Haiku (system_prompt), what context to give it per hostel (context),
# and how to write the result back onto the hostel (apply).
# ---------------------------------------------------------------------------

VIEW_TYPE_VOCAB = [
    "ocean", "mountain", "lake", "river", "valley", "city", "garden",
    "jungle", "pool", "temple", "cliff", "rooftop_skyline", "countryside",
    "rice_paddy", "desert", "park", "volcano", "other",
]
VIEW_FROM_VOCAB = [
    "room", "rooftop", "common_area", "terrace", "balcony",
    "property_grounds", "restaurant", "pool_area", "cabana", "courtyard", "other",
]

PLACE_TYPE_VOCAB = ["cafe", "nature", "landmark", "nightlife", "beach", "viewpoint", "market", "other"]


def _views_context(h):
    views = h.get("views", {})
    return {
        "name": h.get("name"),
        "original_view_type": views.get("view_type"),
        "original_view_from": views.get("view_from"),
        "vibe_profile": h.get("vibe_profile"),
        "reviews_summary": h.get("reviews_summary"),
    }


def _views_apply(h, result):
    old_type = h["views"].get("view_type")
    old_from = h["views"].get("view_from")
    h["views"]["view_type"] = result["view_type"]
    h["views"]["view_from"] = result["view_from"]
    h["views"]["original_free_text"] = {"view_type": old_type, "view_from": old_from}


def _party_level_context(h):
    return {
        "name": h.get("name"),
        "vibe_tags": h.get("vibe_tags"),
        "reviews_summary": h.get("reviews_summary"),
        "social_vibe": h.get("social_vibe"),
        "flagged_issues": h.get("flagged_issues"),
        "vibe_profile": h.get("vibe_profile"),
    }


def _party_level_apply(h, result):
    new_level = result["party_level"]
    h["social_vibe"]["party_level"] = new_level
    h["social_vibe"]["party_level_reclassification_note"] = (
        f"Reclassified from 'low' to '{new_level}' (confidence: {result['confidence']}): {result['reasoning']}"
    )


def _boutique_nearby_context(h):
    return {
        "name": h.get("name"),
        "raw_nearby": h.get("location", {}).get("nearby"),
        "accommodation_type": h.get("accommodation_type"),
        "vibe_tags": h.get("vibe_tags"),
        "facilities": h.get("facilities"),
        "exclusive_features": h.get("exclusive_features"),
        "price_range_usd": h.get("price_range_usd"),
    }


def _boutique_nearby_apply(h, result):
    h["is_boutique_style"] = result["is_boutique_style"]
    if h.get("location", {}).get("nearby"):
        h["location"]["nearby_raw_text"] = h["location"]["nearby"]
        h["location"]["nearby"] = result["nearby"]


NORMALIZE_TASKS = {
    "views": {
        "filter": lambda h: h.get("views", {}).get("has_view") is True,
        "system_prompt": f"""You normalize free-text hostel view descriptions into fixed controlled
vocabularies, using ONLY the data given.

view_type must be a list using ONLY these values: {VIEW_TYPE_VOCAB}
view_from must be a list using ONLY these values: {VIEW_FROM_VOCAB}

Rules:
- Base your answer ONLY on the existing free-text view_type/view_from and any other context given.
  Do not invent details not implied by the source text.
- A hostel can genuinely have more than one view type or be visible from more than one place —
  return every value that's genuinely supported by the source text, not just one.
- If the source text mentions a view/location concept not covered by the vocab, use "other" and
  do not fabricate a new category.
- If the original view_from/view_type is null/missing despite has_view being true, use your best
  judgment from other context fields — but if there's truly no signal, return an empty list.
- Output ONLY valid JSON: {{"view_type": [...], "view_from": [...]}}
No markdown fences, no other text.""",
        "context": _views_context,
        "apply": _views_apply,
        "max_tokens": 200,
        "label": lambda h: h["name"],
    },
    "party_level": {
        "filter": lambda h: h.get("social_vibe", {}).get("party_level") == "low",
        "system_prompt": """You classify a hostel's true social/party level using ONLY the data given to you.

Two categories to choose between:
- "none": the hostel is genuinely quiet/silent with essentially no social or party element.
- "low": the hostel has SOME light social activity — this is the default unless there's a clear
  explicit "none" signal.

Rules:
- Base your answer ONLY on the data given. Do not invent or assume facts not present.
- Default to "low" unless there's a genuinely clear signal of "none".
- Also return a confidence: "high", "medium", or "low" (a human should double check "low").
- Output ONLY valid JSON: {"party_level": "none" | "low", "confidence": "high" | "medium" | "low", "reasoning": "one sentence"}
No markdown fences, no other text.""",
        "context": _party_level_context,
        "apply": _party_level_apply,
        "max_tokens": 200,
        "label": lambda h: h["name"],
    },
    "boutique_nearby": {
        "filter": lambda h: True,  # runs over all hostels — boutique classification applies to every one
        "system_prompt": f"""You do two things given a hostel's existing data, using ONLY the data given:

1. Parse the `raw_nearby` list (free-text place names, often with informal distance/time embedded)
   into a structured list. For each entry: "name" (place name, distance/time text removed), "type"
   (one of {PLACE_TYPE_VOCAB}), "distance_km" (numeric km estimate, ~4.5 km/h walking pace to convert
   time, or null if no real signal), "walkable" (true if distance_km <= 3.0 or source says "walk",
   false if > 3.0, null if unknown).
2. Classify "is_boutique_style": true if accommodation_type/vibe_tags/facilities/exclusive_features
   clearly signal a boutique/design-focused/upscale property, false by default otherwise (boutique is
   the exception, not the default).

Output ONLY valid JSON: {{"nearby": [...], "is_boutique_style": true|false}}
No markdown fences, no other text.""",
        "context": _boutique_nearby_context,
        "apply": _boutique_nearby_apply,
        "max_tokens": 500,
        "label": lambda h: h["name"],
    },
}


def run_normalize(task_name: str):
    if task_name not in NORMALIZE_TASKS:
        print(f"Unknown task '{task_name}'. Available: {', '.join(NORMALIZE_TASKS)}")
        sys.exit(1)

    task = NORMALIZE_TASKS[task_name]
    hostels = load_hostels()
    to_process = [h for h in hostels if task["filter"](h)]
    print(f"[{task_name}] Found {len(to_process)} hostels to process.\n")

    for i, h in enumerate(to_process, 1):
        try:
            context = task["context"](h)
            result = call_haiku(task["system_prompt"], context, task["max_tokens"])
            task["apply"](h, result)
            print(f"[{i}/{len(to_process)}] {task['label'](h)}")
            save_hostels(hostels)
        except Exception as e:
            print(f"[{i}/{len(to_process)}] {h.get('name')} FAILED: {e}")
            time.sleep(2)
            continue

    print(f"\n[{task_name}] Done.")


# ---------------------------------------------------------------------------
# MERGE — apply already-gathered research (from Agent subagents doing real
# WebSearch/WebFetch, or any other source) into hostels.json. See module
# docstring. New fields only need a new line in MERGE_FIELD_MAP, not a new
# script.
# ---------------------------------------------------------------------------

# Maps a top-level key in a results JSON entry -> where it's written on the
# hostel dict, as a path of nested keys. Add a line here for any future
# field a research batch produces — everything else about `merge` stays
# the same.
MERGE_FIELD_MAP = {
    "bed_bug_reports": ("services", "bed_bug_reports"),
    "lockers": ("services", "lockers"),
    "hair_dryer_available": ("services", "hair_dryer_available"),
    "clothes_drying_facility": ("services", "clothes_drying_facility"),
    "curfew_policy": ("services", "curfew_policy"),
    "nearby": ("location", "nearby"),
}


def run_merge(results_path: str, batch_name: str):
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    hostels = load_hostels()
    by_id = {h["id"]: h for h in hostels}

    applied = 0
    field_counts = {}
    for r in results:
        h = by_id.get(r["id"])
        if h is None:
            print(f"WARNING: id {r['id']} not found in hostels.json, skipped")
            continue

        for key, value in r.items():
            if key in ("id", "sources"):
                continue
            if key not in MERGE_FIELD_MAP:
                print(f"WARNING: unknown field '{key}' on hostel {r['id']} — add it to MERGE_FIELD_MAP to apply it. Skipped.")
                continue
            top, sub = MERGE_FIELD_MAP[key]
            h.setdefault(top, {})[sub] = value
            field_counts.setdefault(key, {"true": 0, "false": 0, "populated": 0, "null": 0})
            if value is True:
                field_counts[key]["true"] += 1
            elif value is False:
                field_counts[key]["false"] += 1
            elif value not in (None, [], {}):
                field_counts[key]["populated"] += 1
            else:
                field_counts[key]["null"] += 1

        if "sources" in r:
            h.setdefault("research_sources", {})[batch_name] = r["sources"]

        applied += 1

    save_hostels(hostels)
    print(f"[merge:{batch_name}] Applied {applied} hostel results from {results_path}.\n")
    print("Field coverage in this batch:")
    for field, counts in field_counts.items():
        print(f"  {field}: {counts}")


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VibeMatch hostel data enrichment toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    p_norm = sub.add_parser("normalize", help="Re-read a hostel's own existing data and normalize/reclassify a field (no new research)")
    p_norm.add_argument("task", choices=list(NORMALIZE_TASKS.keys()))

    p_merge = sub.add_parser("merge", help="Merge a research-results JSON file (from real web research) into hostels.json")
    p_merge.add_argument("results_file")
    p_merge.add_argument("--batch-name", required=True, help="Label for this batch, used as the key under research_sources and shown in the coverage report")

    args = parser.parse_args()

    if args.command == "normalize":
        run_normalize(args.task)
    elif args.command == "merge":
        run_merge(args.results_file, args.batch_name)


if __name__ == "__main__":
    main()
