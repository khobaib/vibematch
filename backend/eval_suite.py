"""
eval_suite.py

Task #8 (DECISIONS_LOG.md): an automated eval suite seeded from
DECISIONS_LOG.md's 🟢 RESOLVED entries — each case is a regression test
for a real bug that was actually found and fixed, so it can never
silently come back unnoticed. This is deliberately a different tool from
validate.py: validate.py prints score breakdowns for a HUMAN to read and
judge; this file makes ASSERTIONS and prints a pass/fail summary that
needs no human in the loop. No new dependency (no pytest) — a plain
custom runner, matching the project's existing dependency-free style.

THREE TIERS, to work around the same non-determinism/reachability issues
already documented elsewhere in this project:

  TIER 1 (unit, fully deterministic, no API calls at all) — hand-crafted
  synthetic hostel dicts + hand-crafted intent dicts fed straight into
  score_hostel(). Exercises one specific piece of scoring LOGIC in
  isolation. Can run anywhere, every time, with zero flakiness.

  TIER 2 (integration, needs live Claude only) — real hostels.json via
  match_hostels(), either with a hand-crafted intent dict (deterministic)
  or a live parse_intent() call asserting on ROBUST outcomes (e.g. "this
  field got set at all") rather than exact wording, since intent parsing
  is documented as not perfectly deterministic run to run.

  TIER 3 (integration, needs live Claude AND live Voyage) — the semantic
  layer. This sandbox cannot reach api.voyageai.com (see DECISIONS_LOG.md's
  Voyage-unreachable correction entry) — these cases auto-detect
  reachability via a real embed_query() probe and report SKIPPED (not
  FAILED) when Voyage isn't reachable, rather than giving a false-negative
  failure for an environment limitation. Run from an environment where
  Voyage is reachable to actually exercise these.

USAGE:
    python eval_suite.py            # runs everything (tier 3 auto-skips if Voyage unreachable)
    python eval_suite.py --tier 1   # only unit cases
    python eval_suite.py --tier 2   # only Claude-integration cases
    python eval_suite.py --tier 3   # only Voyage cases (reports SKIPPED here)
"""

import sys
import argparse
import copy

sys.path.insert(0, ".")

from matching import load_hostels, match_hostels, score_hostel


# ---------------------------------------------------------------------------
# Tiny custom runner
# ---------------------------------------------------------------------------

class EvalCase:
    def __init__(self, name, tier, fn, source):
        self.name = name
        self.tier = tier
        self.fn = fn
        self.source = source  # which DECISIONS_LOG.md entry this regression-tests


CASES = []


def case(name, tier, source):
    def decorator(fn):
        CASES.append(EvalCase(name, tier, fn, source))
        return fn
    return decorator


def breakdown_reasons(result):
    return [e["reason"] for e in result["breakdown"]]


def points_for(result, substring):
    """Sum of points across all breakdown entries whose reason contains substring."""
    return sum(e["points"] for e in result["breakdown"] if substring in e["reason"])


def has_reason(result, substring):
    return any(substring in e["reason"] for e in result["breakdown"])


# ---------------------------------------------------------------------------
# TIER 1 — unit cases (score_hostel on synthetic hostel/intent, no API calls)
# ---------------------------------------------------------------------------

BASE_HOSTEL = {
    "id": 9999, "name": "Test Hostel", "city": "Testville", "region": "Test Region",
    "country": "Testland", "price_range_usd": {"min": 10, "max": 20},
    "vibe_tags": [], "social_vibe": {"guest_type": [], "party_level": "low"},
    "services": {}, "location": {}, "views": {}, "flagged_issues": [],
}


def hostel(**overrides):
    h = copy.deepcopy(BASE_HOSTEL)
    for key, value in overrides.items():
        if isinstance(value, dict) and key in h and isinstance(h[key], dict):
            h[key].update(value)
        else:
            h[key] = value
    return h


BASE_INTENT = {
    "location": None, "budget_max": None, "budget_flexibility": "strict",
    "stay_duration_signal": "unknown", "party_preference": "neutral",
    "daytime_vibe_preference": None, "evening_vibe_preference": None,
    "vibe_tags": [], "traveler_profile": [],
}


def intent(**overrides):
    i = copy.deepcopy(BASE_INTENT)
    i.update(overrides)
    return i


@case(
    "Bed bug penalty fires regardless of query content",
    tier=1,
    source="🟢 RESOLVED — services fields wired into matching.py (bed_bug_reports unconditional)",
)
def _():
    h = hostel(services={"bed_bug_reports": True})
    # Query says nothing about safety/cleanliness at all.
    result = score_hostel(h, intent(vibe_tags=["ocean view"]))
    assert points_for(result, "bed bug") == -15, f"expected -15 bed bug penalty, got breakdown: {breakdown_reasons(result)}"


@case(
    "Confirmed-clean bed bug bonus only fires when safety/comfort is actually raised",
    tier=1,
    source="🟢 RESOLVED — services fields wired into matching.py + comfort keyword extension",
)
def _():
    h = hostel(services={"bed_bug_reports": False})
    unrelated = score_hostel(h, intent(vibe_tags=["ocean view"]), raw_query="ocean view hostel")
    assert not has_reason(unrelated, "no credible bed bug"), \
        f"bonus should NOT fire with no safety/comfort signal, got: {breakdown_reasons(unrelated)}"

    comfort = score_hostel(h, intent(vibe_tags=["comfortable"]), raw_query="a comfortable hostel")
    assert has_reason(comfort, "no credible bed bug"), \
        f"bonus SHOULD fire on 'comfortable' (explicit comfort-keyword extension), got: {breakdown_reasons(comfort)}"


@case(
    "Curfew: strong '24/7' language penalizes harder (-20) than a general mention (-8)",
    tier=1,
    source="🟢 RESOLVED — Curfew strong-vs-general penalty tier",
)
def _():
    h = hostel(services={"curfew_policy": "11pm curfew, gates locked overnight"})
    strong = score_hostel(h, intent(), raw_query="I need 24/7 access, no curfew")
    general = score_hostel(h, intent(), raw_query="does this place have a curfew?")
    strong_penalty = points_for(strong, "curfew")
    general_penalty = points_for(general, "curfew")
    assert strong_penalty == -20, f"expected -20 for strong 24/7 language, got {strong_penalty}: {breakdown_reasons(strong)}"
    assert general_penalty == -8, f"expected -8 for general mention, got {general_penalty}: {breakdown_reasons(general)}"


@case(
    "Curfew: 'no strict curfew' phrasing is NOT wrongly read as a real curfew",
    tier=1,
    source="🟢 RESOLVED — 'no curfew' detection regex fix (missed 'no strict/formal/explicit curfew' phrasings)",
)
def _():
    h = hostel(services={"curfew_policy": "no strict curfew, but quiet hours after 11pm"})
    result = score_hostel(h, intent(), raw_query="need 24/7 access, no curfew")
    assert has_reason(result, "no curfew / 24hr access"), \
        f"'no strict curfew' should score as a real no-curfew match, not a penalty: {breakdown_reasons(result)}"
    assert points_for(result, "curfew") == 8, f"expected +8, got breakdown: {breakdown_reasons(result)}"


@case(
    "Lockers bonus fires from raw_query even when vibe_tags paraphrased away the literal word",
    tier=1,
    source="🟢 RESOLVED — raw_query fallback for paraphrasing gap (Claude drops 'lockers' from tags)",
)
def _():
    h = hostel(services={"lockers": {"available": True}})
    # Simulates the real observed bug: Claude's parser reduced "secure lockers" to just the tag "secure".
    result = score_hostel(h, intent(vibe_tags=["secure"]), raw_query="clean hostel with secure lockers please")
    assert has_reason(result, "secure lockers"), \
        f"locker bonus should fire via raw_query fallback, got: {breakdown_reasons(result)}"


@case(
    "Negation conflict: 'not_party' vs a hostel tagged 'party_hostel' penalizes, doesn't match",
    tier=1,
    source="🟢 RESOLVED — Partial vibe-tag matching didn't understand negation",
)
def _():
    h = hostel(vibe_tags=["party_hostel"])
    result = score_hostel(h, intent(vibe_tags=["not_party"]))
    assert has_reason(result, "conflicting vibe"), f"expected a conflict penalty, got: {breakdown_reasons(result)}"
    assert points_for(result, "matches your vibe") == 0, \
        f"should NOT also register as a positive match, got: {breakdown_reasons(result)}"


@case(
    "'avoid' party_preference treats 'low' as a real miss, not a near-perfect match",
    tier=1,
    source="🟢 RESOLVED — 'low' party_level was treated as a perfect match for 'avoid', when it shouldn't be",
)
def _():
    h = hostel(social_vibe={"party_level": "low"})
    result = score_hostel(h, intent(party_preference="avoid"))
    party_points = points_for(result, "party vibe")
    assert party_points == -10, f"expected -10 (real miss under 'avoid'), got {party_points}: {breakdown_reasons(result)}"


@case(
    "Budget: strict ceiling penalizes going over; approximate gives flat credit within a 20% tolerance zone, softer penalty beyond it",
    tier=1,
    source="🟢 RESOLVED — 'Budget around $X' was scored identically to 'budget under $X'",
)
def _():
    # budget_max=10 -> approximate tolerance ceiling = 10 * 1.2 = $12.
    over_budget = hostel(price_range_usd={"min": 13, "max": 20})       # $13 — outside the $12 tolerance ceiling
    within_tolerance = hostel(price_range_usd={"min": 11, "max": 20})  # $11 — inside it

    strict = score_hostel(over_budget, intent(budget_max=10, budget_flexibility="strict"))
    assert points_for(strict, "budget") == -15, f"strict over-budget should be -15, got: {breakdown_reasons(strict)}"

    approx_over = score_hostel(over_budget, intent(budget_max=10, budget_flexibility="approximate"))
    assert has_reason(approx_over, "meaningfully above"), \
        f"expected the softer over-tolerance penalty wording, got: {breakdown_reasons(approx_over)}"
    assert points_for(approx_over, "target") == -8, f"expected -8, got: {breakdown_reasons(approx_over)}"

    approx_in_zone = score_hostel(within_tolerance, intent(budget_max=10, budget_flexibility="approximate"))
    assert has_reason(approx_in_zone, "is close to your"), \
        f"expected flat in-zone credit wording, got: {breakdown_reasons(approx_in_zone)}"
    assert points_for(approx_in_zone, "target") == 20, f"expected +20 flat credit, got: {breakdown_reasons(approx_in_zone)}"


@case(
    "Missing price data is flagged explicitly, not silently neutral",
    tier=1,
    source="🟢 RESOLVED — Missing price data scored as silently neutral instead of being flagged",
)
def _():
    h = hostel(price_range_usd=None)
    result = score_hostel(h, intent(budget_max=15))
    assert has_reason(result, "price not listed"), f"expected an explicit missing-price flag, got: {breakdown_reasons(result)}"


@case(
    "Day/night split score table: 'low' under 'quiet' preference is neutral (0), not a penalty",
    tier=1,
    source="🟢 RESOLVED — 0-point wording bug in split day/night party scoring",
)
def _():
    h = hostel(social_vibe={"daytime_party_level": "low", "evening_party_level": "high"})
    result = score_hostel(h, intent(daytime_vibe_preference="quiet", evening_vibe_preference="social"))
    assert points_for(result, "daytime vibe") == 0, f"expected 0 (neutral), got: {breakdown_reasons(result)}"
    assert has_reason(result, "neutral match"), f"expected the neutral-wording branch, got: {breakdown_reasons(result)}"
    assert points_for(result, "evening vibe") == 5, f"expected +5 (max bonus, halved from 10), got: {breakdown_reasons(result)}"


# ---------------------------------------------------------------------------
# TIER 2 — integration cases, real hostels.json, live Claude only
# ---------------------------------------------------------------------------

@case(
    "Bangkok party query returns real party hostels, not zero results",
    tier=2,
    source="🟢 RESOLVED — Bangkok had no genuine party hostel, causing valid searches to return zero results",
)
def _(hostels):
    result = match_hostels(
        intent(location="Bangkok", party_preference="prefer_party", vibe_tags=["party", "nightlife"]),
        hostels, top_n=5,
    )
    assert result["total_matches"] >= 2, f"expected at least 2 matches, got {result['total_matches']}"
    top_names = {m["name"] for m in result["results"][:2]}
    known_party_hostels = {"Nomads Bangkok Khao San Road Hostel", "Revolution Khao San by The Bliss"}
    assert top_names & known_party_hostels, f"expected a known real party hostel on top, got: {top_names}"


@case(
    "Continent-level search ('Europe') returns non-zero matches",
    tier=2,
    source="🟢 RESOLVED — Continent-level location searches returned zero results",
)
def _(hostels):
    result = match_hostels(intent(location="Europe"), hostels, top_n=5)
    assert result["total_matches"] > 0, "expected non-zero matches for a continent-level search"


@case(
    "Compound location string 'Weligama, Sri Lanka' still matches the city",
    tier=2,
    source="🟢 RESOLVED — Compound location strings ('City, Country') broke exact-city matching",
)
def _(hostels):
    result = match_hostels(intent(location="Weligama, Sri Lanka"), hostels, top_n=5)
    assert result["total_matches"] > 0, "expected at least the Weligama hostel to match"
    assert any("Weligama" in m["city"] for m in result["results"]), \
        f"expected a Weligama hostel in results, got cities: {[m['city'] for m in result['results']]}"


@case(
    "Live parse_intent() detects the daytime/evening split for a genuinely dual-mode query",
    tier=2,
    source="🟢 RESOLVED — Task #7 refactor + Fix B daytime/evening split fields",
)
def _(hostels):
    from main import parse_intent
    parsed = parse_intent("somewhere I can focus during the day but still meet people over dinner")
    # Tolerant assertion: only checks the fields got set at all, not exact vibe_tags
    # wording, per the documented intent-parsing non-determinism.
    assert parsed.get("daytime_vibe_preference") == "quiet", f"expected daytime='quiet', got: {parsed}"
    assert parsed.get("evening_vibe_preference") == "social", f"expected evening='social', got: {parsed}"


@case(
    "Live parse_intent() leaves the split fields null for a single-mode query",
    tier=2,
    source="🟢 RESOLVED — daytime/evening split fields only set when genuinely dual-mode",
)
def _(hostels):
    from main import parse_intent
    parsed = parse_intent("chill hostel, not too party")
    assert parsed.get("daytime_vibe_preference") is None, f"expected null, got: {parsed}"
    assert parsed.get("evening_vibe_preference") is None, f"expected null, got: {parsed}"


# ---------------------------------------------------------------------------
# TIER 3 — integration cases, needs live Claude AND live Voyage
# ---------------------------------------------------------------------------

def _voyage_reachable():
    try:
        from semantic_similarity import embed_query
        embed_query("reachability probe")
        return True
    except Exception:
        return False


@case(
    "Semantic layer surfaces 'quiet'-tagged hostels for 'calm surroundings' with no literal tag overlap",
    tier=3,
    source="🟢 RESOLVED — Vibe tag matching was pure text/substring comparison, not semantic understanding",
)
def _(hostels):
    from main import parse_intent
    from semantic_similarity import load_hostel_embeddings
    embeddings = load_hostel_embeddings()
    parsed = parse_intent("somewhere with calm surroundings to relax")
    result = match_hostels(
        parsed, hostels, top_n=5,
        raw_query="somewhere with calm surroundings to relax", hostel_embeddings=embeddings,
    )
    assert any(has_reason(m, "semantically matches") for m in result["results"]), \
        "expected at least one semantic-match line in the top 5"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(tiers):
    hostels = load_hostels()
    voyage_ok = _voyage_reachable() if 3 in tiers else None

    passed, failed, skipped = 0, 0, 0
    for c in CASES:
        if c.tier not in tiers:
            continue
        if c.tier == 3 and not voyage_ok:
            print(f"SKIP  [{c.name}] — Voyage not reachable from this environment")
            skipped += 1
            continue
        try:
            if c.tier == 1:
                c.fn()
            else:
                c.fn(hostels)
            print(f"PASS  [{c.name}]")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  [{c.name}]")
            print(f"      {e}")
            print(f"      (regression-tests: {c.source})")
            failed += 1
        except Exception as e:
            print(f"ERROR [{c.name}] — {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="VibeMatch automated eval suite")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=None,
                         help="Run only this tier (default: all)")
    args = parser.parse_args()
    tiers = [args.tier] if args.tier else [1, 2, 3]
    ok = run(tiers)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
