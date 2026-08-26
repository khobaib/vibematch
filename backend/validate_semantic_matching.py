"""
validate_semantic_matching.py

Task #6: validate the new semantic-similarity layer (Task #5) against
known tech-debt cases from DECISIONS_LOG.md, plus a battery of queries
specifically designed to probe where semantic scoring and the existing
structured scoring (vibe_tags, party_preference) might disagree.

This needs BOTH a live Claude call (intent parsing) and a live Voyage call
(query embedding), so it must be run somewhere both APIs are reachable —
not from a sandbox with restricted network egress.

What it does, per test case:
1. Runs the real parse_intent() -> match_hostels() pipeline (same code
   path as the actual /search endpoint) with the given raw query.
2. Prints the top 5 results with full breakdowns.
3. Flags any result where a NEGATIVE structured-scoring entry (e.g. a
   party-preference mismatch) and a POSITIVE semantic entry both appear —
   this is exactly the kind of disagreement logged as an open item in
   DECISIONS_LOG.md, and each flagged case is worth a human read, not an
   automatic pass/fail.

This is a diagnostic tool, not a pass/fail test suite — the point is to
surface real examples for a human to judge, the same way every other
adversarial case in DECISIONS_LOG.md was found (real query -> real
response -> human reads it and decides if it's right).
"""

import sys
import json

sys.path.insert(0, ".")

from main import parse_intent
from matching import load_hostels, match_hostels
from semantic_similarity import load_hostel_embeddings

TEST_CASES = [
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
]


def run():
    hostels = load_hostels()
    hostel_embeddings = load_hostel_embeddings()
    print(f"Loaded {len(hostels)} hostels, {len(hostel_embeddings)} embeddings.\n")
    print("=" * 100)

    for case in TEST_CASES:
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


if __name__ == "__main__":
    run()
