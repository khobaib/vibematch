"""
VibeMatch matching engine.

Takes the structured intent JSON (output of the Claude intent parser)
and scores every hostel in hostels.json against it.

This file is intentionally standalone — no FastAPI imports — so you can
test it directly with `python matching.py` before wiring it into main.py.
"""

import json


def load_hostels(path="hostels.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def score_hostel(hostel: dict, intent: dict) -> dict:
    """
    Returns a dict: {"score": int, "reasons": [str, ...]}

    Score is a simple additive point system — not fancy, but transparent
    and easy to debug. Each rule adds points and records WHY it matched,
    which becomes the raw material for "Why we matched this" later.
    """
    score = 0
    reasons = []

    # --- 1. Location match (checks city, region, and country) ---
    location = intent.get("location")
    if location:
        location = location.lower()
        hostel_city = (hostel.get("city") or "").lower()
        hostel_region = (hostel.get("region") or "").lower()
        hostel_country = (hostel.get("country") or "").lower()

        if location in hostel_city:
            score += 30
            reasons.append(f"located in {hostel['city']}, matching your requested location")
        elif hostel_region and location in hostel_region:
            score += 25
            reasons.append(f"located in {hostel['region']}, matching your requested region")
        elif location in hostel_country:
            score += 15
            reasons.append(f"located in {hostel['country']}, matching your requested location")
        else:
            nearby_towns = [t.lower() for t in hostel.get("location", {}).get("nearby_towns", [])]
            matched_nearby = [t for t in nearby_towns if location in t or t in location]
            if matched_nearby:
                score += 22
                reasons.append(f"close to {matched_nearby[0].title()}, near your requested location")

    # --- 2. Budget match ---
    budget_max = intent.get("budget_max")
    if budget_max:
        price_range = hostel.get("price_range_usd")
        if price_range and price_range.get("min") is not None:
            cheapest_bed = price_range["min"]
            if cheapest_bed <= budget_max:
                score += 20
                reasons.append(f"cheapest bed (${cheapest_bed}) fits your ${budget_max} budget")
            else:
                score -= 15  # penalize but don't hard-exclude — traveler might flex

    # --- 3. Vibe tag overlap ---
    vibe_tags = set(t.lower() for t in intent.get("vibe_tags", []))
    hostel_tags = set(t.lower() for t in hostel.get("vibe_tags", []))
    matched_tags = vibe_tags & hostel_tags
    if matched_tags:
        score += 10 * len(matched_tags)
        reasons.append(f"matches your vibe: {', '.join(sorted(matched_tags))}")

    # Also check partial/substring matches (vibe_tags are often multi-word)
    for vt in vibe_tags:
        for ht in hostel_tags:
            if vt != ht and (vt in ht or ht in vt):
                score += 4
                reasons.append(f"related vibe match: '{vt}' ~ '{ht}'")

    # --- 4. Traveler profile overlap ---
    traveler_profile = set(t.lower() for t in intent.get("traveler_profile", []))
    guest_type = set(t.lower() for t in hostel.get("social_vibe", {}).get("guest_type", []))
    matched_profile = traveler_profile & guest_type
    if matched_profile:
        score += 8 * len(matched_profile)
        reasons.append(f"popular with travelers like you: {', '.join(sorted(matched_profile))}")

    # --- 5. Stay duration signal ---
    stay_signal = intent.get("stay_duration_signal")
    if stay_signal == "long_term":
        if hostel.get("social_vibe", {}).get("good_for_remote_work"):
            score += 6
            reasons.append("good for remote work / longer stays")
        if "long_term_traveler" in guest_type or "long_term_visa_stayers" in guest_type:
            score += 6
            reasons.append("popular with long-term travelers")
    elif stay_signal == "short_term":
        if "transit_traveler" in guest_type:
            score += 6
            reasons.append("well suited for a short transit stay")

    return {"score": score, "reasons": reasons}


def match_hostels(intent: dict, hostels: list, top_n: int = 10) -> list:
    """
    STEP 1 — Hard filter: if a location was specified, only consider
    hostels that are actually in that city/region/country. Location is
    a "must match" filter, not a ranking signal — it should never lose
    to a strong vibe/budget match from the wrong place.

    STEP 2 — Soft ranking: among the location-filtered hostels (or all
    hostels, if no location was given), score by budget/vibe/profile
    and sort descending.
    """
    location = (intent.get("location") or "").lower()

    if location:
        filtered = []
        for h in hostels:
            hostel_city = (h.get("city") or "").lower()
            hostel_region = (h.get("region") or "").lower()
            hostel_country = (h.get("country") or "").lower()
            nearby_towns = [t.lower() for t in h.get("location", {}).get("nearby_towns", [])]
            if (location in hostel_city or location in hostel_region
                    or location in hostel_country
                    or any(location in nt or nt in location for nt in nearby_towns)):
                filtered.append(h)
        hostels = filtered

    results = []
    for hostel in hostels:
        result = score_hostel(hostel, intent)
        if result["score"] > 0:  # drop zero/negative matches entirely
            results.append({
                "id": hostel["id"],
                "name": hostel["name"],
                "city": hostel["city"],
                "country": hostel["country"],
                "score": result["score"],
                "reasons": result["reasons"],
                "price_range_usd": hostel.get("price_range_usd"),
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]


# --- Quick manual test when running this file directly ---
if __name__ == "__main__":
    hostels = load_hostels()

    # Simulate an intent parser output for testing
    test_intent = {
        "location": "Goa",
        "budget_max": 15,
        "stay_duration_signal": "short_term",
        "vibe_tags": ["party_hostel", "social"],
        "traveler_profile": ["solo_backpacker", "party_travelers"]
    }

    matches = match_hostels(test_intent, hostels)

    print(f"Found {len(matches)} matches for test query:\n")
    for m in matches:
        print(f"[{m['score']}] {m['name']} ({m['city']}, {m['country']})")
        for r in m["reasons"]:
            print(f"    - {r}")
        print()
