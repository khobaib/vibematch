"""
validate.py

Single toolkit for all matching-engine validation/test scripts. Replaces
three separate one-off files (validate_semantic_matching.py,
validate_daynight_split.py, validate_backlog_fields.py) — same
consolidation pattern already applied once to the data-enrichment scripts
(see data_tools.py's module docstring for the full reasoning). Writing a
brand new validate_<whatever>.py for every future scoring change wasn't
going to scale any better than the enrichment scripts did.

Each validation concern is now a SUITE in the SUITES registry below —
adding a future one means adding one function + one registry entry, not a
new file. All synthetic test fixtures live together in one file,
test_fixtures/synthetic_test_data.json, under separate top-level sections
(one per suite that needs fake data) — see that file's `_README`.

USAGE:
    python validate.py semantic         # Task #6 tech-debt cases + new services-field checks
                                         # (needs live Claude AND Voyage — Voyage is NOT reachable
                                         # from this sandbox, run this suite from an environment
                                         # where it is)
    python validate.py daynight         # daytime/evening split-scoring mechanism (synthetic data)
    python validate.py backlog_fields   # 7 backlogged fields' scoring logic (synthetic data)
    python validate.py all              # runs every suite in sequence

Suites that use a synthetic fixture (daynight, backlog_fields) NEVER write
to hostels.json — they deep-copy the real hostel list in memory, overlay
fake values onto the copy only, and each ends with an explicit sanity
check confirming hostels.json on disk is unmodified.
"""

import copy
import json
import sys
import argparse

sys.path.insert(0, ".")

from matching import load_hostels, match_hostels

FIXTURES_PATH = "test_fixtures/synthetic_test_data.json"


def _load_fixture_section(section: str) -> dict:
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    section_data = data[section]
    print(f"Fixture warning ({section}): {section_data['_WARNING']}\n")
    return section_data["fixture"]


def _print_top(outcome, n=5):
    for m in outcome["results"][:n]:
        print(f"  [{m['score']:>3}] {m['name']}")
        for e in m["breakdown"]:
            sign = "+" if e["points"] >= 0 else ""
            print(f"      {sign}{e['points']:>3}  {e['reason']}")
        print()


def _sanity_check_unmodified(original_hostels):
    still_same = original_hostels == load_hostels()
    print("Sanity check: hostels.json on disk is unmodified —",
          "confirmed" if still_same else "!!! MODIFIED, INVESTIGATE !!!")


# ---------------------------------------------------------------------------
# SUITE: semantic — Task #6 tech-debt cases + services-field keyword checks.
# Needs live Claude (intent parsing) AND live Voyage (query embedding).
# ---------------------------------------------------------------------------

SEMANTIC_TEST_CASES = [
    {
        "query": "somewhere with calm surroundings to relax",
        "why": "DECISIONS_LOG.md case: 'calm surroundings' (query) vs 'quiet' (hostel tag) — "
               "originally scored zero vibe credit because neither string contains the other. "
               "Semantic layer should now surface quiet-tagged hostels even without exact overlap.",
    },
    {
        "query": "hostel near Weligama, Sri Lanka",
        "why": "DECISIONS_LOG.md non-determinism case — intent parsing varies run to run. "
               "Checking whether the semantic score for the same raw query text stays stable "
               "even when Claude's vibe_tags extraction drifts.",
    },
    {
        "query": "a chill hostel in Goa good for remote work, not too partyish",
        "why": "The exact query that surfaced the semantic-vs-structured disagreement pattern "
               "logged as a new OPEN item — re-running to see if it reproduces and how often.",
    },
    {
        "query": "somewhere I can focus during the day but still meet people over dinner",
        "why": "No obvious single vibe_tag captures this balance — designed to test whether "
               "semantic matching adds real value beyond what tag matching alone could find.",
    },
    {
        "query": "party hostel in Bangkok, want the nightlife",
        "why": "DECISIONS_LOG.md resolved case (previously 0 results, fixed by adding real "
               "party hostels). Regression check: does the semantic layer help, hurt, or not "
               "materially change this now-working case?",
    },
    {
        "query": "quiet place, absolutely do not want a party hostel",
        "why": "Strong negative party preference. Checking whether the semantic layer ever "
               "overrides or undermines a traveler's explicit, strongly-worded 'avoid' signal.",
    },
    {
        "query": "clean and comfortable hostel with secure lockers, no bed bugs please",
        "why": "Services-field validation: bed_bug_reports (unconditional -15 if true, "
               "keyword-gated +6 if confirmed clean) and lockers (keyword-gated +8/-5). Checking "
               "the always-on bed bug penalty surfaces correctly, and that 'comfortable' "
               "triggers the bed bug bonus as intended.",
    },
    {
        "query": "need 24/7 access, no curfew, with a hair dryer and a place to dry my clothes",
        "why": "Services-field validation: curfew_policy (strong '24/7' language -> -20 penalty "
               "on a real curfew, vs the softer -8 for a general mention), plus "
               "hair_dryer_available and clothes_drying_facility (keyword-gated +6/-4 each). "
               "Checking all three fire together without stepping on each other's entries.",
    },
]


def run_semantic():
    from main import parse_intent
    from semantic_similarity import load_hostel_embeddings

    hostels = load_hostels()
    hostel_embeddings = load_hostel_embeddings()
    print(f"Loaded {len(hostels)} hostels, {len(hostel_embeddings)} embeddings.\n")
    print("=" * 100)

    for case in SEMANTIC_TEST_CASES:
        query = case["query"]
        print(f"\nQUERY: {query!r}")
        print(f"WHY:   {case['why']}\n")

        intent = parse_intent(query)
        print("Parsed intent:", json.dumps(intent, ensure_ascii=False))

        outcome = match_hostels(
            intent, hostels, top_n=5,
            raw_query=query, hostel_embeddings=hostel_embeddings,
        )
        print(f"Total matches: {outcome['total_matches']}\n")

        for m in outcome["results"]:
            print(f"  [{m['score']:>3}] {m['name']} ({m['city']}, {m['country']})")
            has_negative_structured = False
            has_positive_semantic = False
            for entry in m["breakdown"]:
                sign = "+" if entry["points"] >= 0 else ""
                is_semantic = "semantically matches" in entry["reason"]
                print(f"      {sign}{entry['points']:>3}  {entry['reason']}")
                if entry["points"] < 0 and not is_semantic:
                    has_negative_structured = True
                if entry["points"] > 0 and is_semantic:
                    has_positive_semantic = True
            if has_negative_structured and has_positive_semantic:
                print("      ^^^ FLAGGED: negative structured signal + positive semantic signal on the same hostel")
            print()

        print("=" * 100)


# ---------------------------------------------------------------------------
# SUITE: daynight — daytime/evening split-scoring mechanism (Fix B).
# Uses the 'daynight' fixture section. Needs live Claude only (no Voyage).
# ---------------------------------------------------------------------------

DAYNIGHT_QUERY = "somewhere I can focus during the day but still meet people over dinner"


def _apply_daynight_fixture(hostels, fixture):
    overlaid = copy.deepcopy(hostels)
    fixture_ids = {int(k) for k in fixture}
    for h in overlaid:
        if h["id"] in fixture_ids:
            values = fixture[str(h["id"])]
            h.setdefault("social_vibe", {})["daytime_party_level"] = values["daytime_party_level"]
            h["social_vibe"]["evening_party_level"] = values["evening_party_level"]
    return overlaid


def run_daynight():
    from main import parse_intent

    hostels = load_hostels()
    fixture = _load_fixture_section("daynight")

    print(f"QUERY: {DAYNIGHT_QUERY!r}\n")
    intent = parse_intent(DAYNIGHT_QUERY)
    print("Parsed intent:", json.dumps(intent, ensure_ascii=False))
    print(f"Day/night split detected by parser: "
          f"daytime={intent.get('daytime_vibe_preference')!r}, "
          f"evening={intent.get('evening_vibe_preference')!r}\n")

    print("=" * 100)
    print("BEFORE — real hostels.json (daytime_party_level/evening_party_level are null everywhere)")
    print("=" * 100)
    before = match_hostels(intent, hostels, top_n=5, raw_query=DAYNIGHT_QUERY)
    _print_top(before)

    print("=" * 100)
    print(f"AFTER — {len(fixture)} hostels overlaid with SYNTHETIC (fake, random) day/evening values, in-memory only")
    print("=" * 100)
    overlaid_hostels = _apply_daynight_fixture(hostels, fixture)
    after = match_hostels(intent, overlaid_hostels, top_n=5, raw_query=DAYNIGHT_QUERY)
    _print_top(after)

    print("=" * 100)
    _sanity_check_unmodified(hostels)


# ---------------------------------------------------------------------------
# SUITE: backlog_fields — 7 backlogged fields' scoring logic (wifi_quality,
# desk_setup, diy_breakfast_available, kitchen_utensils_quality,
# communal_dinner_available, whatsapp_community_group_available,
# solo_group_ratio). Uses the 'backlog_fields' fixture section. No live API
# calls at all — intents are hand-written, not parsed live.
# ---------------------------------------------------------------------------

BACKLOG_FIELDS_TEST_CASES = [
    {
        "query": "need strong wifi and a proper desk to work from during the day",
        "intent": {"location": None, "vibe_tags": ["wifi", "desk", "work", "focus"], "traveler_profile": ["digital_nomad"]},
        "why": "Tests wifi_quality + desk_setup inside the daytime work-focus combo (step 17).",
    },
    {
        "query": "want to meet people, ideally a hostel with a WhatsApp group and communal dinners",
        "intent": {"location": None, "vibe_tags": ["whatsapp group", "communal dinner", "meet people"], "traveler_profile": ["social_traveler"]},
        "why": "Tests communal_dinner_available + whatsapp_community_group_available + solo_group_ratio inside the evening social-mixing combo (step 18).",
    },
    {
        "query": "somewhere with free breakfast or at least DIY breakfast basics and a decent kitchen",
        "intent": {"location": None, "vibe_tags": ["breakfast", "diy breakfast", "kitchen utensils"], "traveler_profile": ["budget_conscious"]},
        "why": "Tests the food-self-sufficiency combo (step 19) — free_breakfast is REAL data here, diy_breakfast_available/kitchen_utensils_quality are synthetic.",
    },
]


def _apply_backlog_fields_fixture(hostels, fixture):
    overlaid = copy.deepcopy(hostels)
    fixture_ids = {int(k) for k in fixture}
    for h in overlaid:
        if h["id"] in fixture_ids:
            values = fixture[str(h["id"])]
            for top_key, sub_values in values.items():
                h.setdefault(top_key, {}).update(sub_values)
    return overlaid


def run_backlog_fields():
    hostels = load_hostels()
    fixture = _load_fixture_section("backlog_fields")
    overlaid_hostels = _apply_backlog_fields_fixture(hostels, fixture)

    for case in BACKLOG_FIELDS_TEST_CASES:
        print("=" * 100)
        print(f"QUERY: {case['query']!r}")
        print(f"WHY:   {case['why']}\n")

        print("--- BEFORE (real hostels.json — these fields are null everywhere) ---")
        before = match_hostels(case["intent"], hostels, top_n=4, raw_query=case["query"])
        _print_top(before, n=4)

        print(f"--- AFTER ({len(fixture)} hostels overlaid with SYNTHETIC values, in-memory only) ---")
        after = match_hostels(case["intent"], overlaid_hostels, top_n=4, raw_query=case["query"])
        _print_top(after, n=4)

    print("=" * 100)
    _sanity_check_unmodified(hostels)


# ---------------------------------------------------------------------------

SUITES = {
    "semantic": run_semantic,
    "daynight": run_daynight,
    "backlog_fields": run_backlog_fields,
}


def main():
    parser = argparse.ArgumentParser(description="VibeMatch matching-engine validation toolkit")
    parser.add_argument("suite", choices=list(SUITES.keys()) + ["all"])
    args = parser.parse_args()

    if args.suite == "all":
        for name, fn in SUITES.items():
            print(f"\n{'#' * 100}\n# SUITE: {name}\n{'#' * 100}\n")
            fn()
    else:
        SUITES[args.suite]()


if __name__ == "__main__":
    main()
