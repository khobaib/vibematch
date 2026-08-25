"""
VibeMatch matching engine.

Takes the structured intent JSON (output of the Claude intent parser)
and scores every hostel in hostels.json against it.

This file is intentionally standalone — no FastAPI imports — so you can
test it directly with `python matching.py` before wiring it into main.py.

KNOWN LIMITATION (tracked for Phase 4):
Location matching uses a manually-curated `nearby_towns` list per hostel
as a stopgap. This does NOT account for actual distance (a nearby_towns
match scores the same whether the place is 2km or 18km away) and does
not scale — it only recognizes place names someone thought to add by hand.
The correct long-term fix is storing real lat/long coordinates per hostel
(e.g. via Google Places API) and geocoding search terms on the fly to
compute real distance. Deferred until Phase 4 data infrastructure work.
"""


import json


# Static country -> continent lookup, used only at query time so we don't
# need to store a redundant "continent" field on every hostel. Countries
# that genuinely span two continents (e.g. Turkey) list both — a search
# for either continent should surface them.
COUNTRY_TO_CONTINENTS = {
    "argentina": ["south america"],
    "australia": ["oceania"],
    "austria": ["europe"],
    "bolivia": ["south america"],
    "brazil": ["south america"],
    "bulgaria": ["europe"],
    "cambodia": ["asia"],
    "chile": ["south america"],
    "colombia": ["south america"],
    "croatia": ["europe"],
    "czech republic": ["europe"],
    "denmark": ["europe"],
    "ecuador": ["south america"],
    "france": ["europe"],
    "germany": ["europe"],
    "greece": ["europe"],
    "hungary": ["europe"],
    "india": ["asia"],
    "indonesia": ["asia"],
    "ireland": ["europe"],
    "italy": ["europe"],
    "laos": ["asia"],
    "latvia": ["europe"],
    "malaysia": ["asia"],
    "morocco": ["africa"],
    "nepal": ["asia"],
    "netherlands": ["europe"],
    "peru": ["south america"],
    "philippines": ["asia"],
    "poland": ["europe"],
    "portugal": ["europe"],
    "serbia": ["europe"],
    "singapore": ["asia"],
    "spain": ["europe"],
    "sri lanka": ["asia"],
    "switzerland": ["europe"],
    "thailand": ["asia"],
    "turkey": ["europe", "asia"],  # transcontinental
    "united kingdom": ["europe"],
    "uruguay": ["south america"],
    "vietnam": ["asia"],
}


def hostel_continents(hostel: dict) -> list:
    country = (hostel.get("country") or "").lower()
    return COUNTRY_TO_CONTINENTS.get(country, [])


def load_hostels(path="hostels.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def score_hostel(hostel: dict, intent: dict, local_price_bounds: tuple = None, semantic_entry: dict = None) -> dict:
    """
    Returns a dict: {"score": int, "breakdown": [{"points": int, "reason": str}, ...]}

    Every point added or subtracted is recorded as its own breakdown entry —
    "score" is just the sum of all entries. This makes the final number fully
    auditable: you can always answer "why did this hostel score 43?" by
    reading the breakdown list, rather than trusting an opaque total.

    local_price_bounds: optional (min, max) of price_range_usd.min across
    the CURRENT candidate pool (i.e. after location filtering already ran
    in match_hostels). Used to score "cheap"/"budget" language relative to
    what's actually available in that search, rather than a fixed global
    dollar amount — $20 is cheap in Amsterdam, expensive in Bangkok, and a
    fixed table can't know that. Whatever geographic grain the traveler
    searched at (city/region/country/continent), the candidate pool is
    already scoped correctly by the time this function runs.

    semantic_entry: optional, pre-computed breakdown entry (see
    compute_semantic_entries()) capturing how well this hostel's
    LLM-written vibe_profile semantically matches the traveler's raw
    free-text query, via Voyage embeddings + cosine similarity. Computed
    once per search (not per hostel) in match_hostels() and passed in
    here so this function stays a pure "given the facts, score them"
    step — it doesn't know or care that an API call happened upstream.
    """
    breakdown = []

    def add(points, reason):
        breakdown.append({"points": points, "reason": reason})

    # --- 1. Location match (checks city, region, and country) ---
    location = intent.get("location")
    if location:
        location = location.lower()
        hostel_city = (hostel.get("city") or "").lower()
        hostel_region = (hostel.get("region") or "").lower()
        hostel_country = (hostel.get("country") or "").lower()

        # Bidirectional substring check. The intent parser sometimes returns
        # compound strings like "Weligama, Sri Lanka" instead of just
        # "Weligama" — a one-directional check (location in hostel_city)
        # fails in that case because the search term is LONGER than the
        # city name, so it can never be "contained within" it. Checking
        # both directions (same pattern already used for nearby_towns)
        # catches the city name wherever it sits inside a longer string.
        if location in hostel_city or (hostel_city and hostel_city in location):
            add(30, f"located in {hostel['city']}, matching your requested location")
        elif hostel_region and (location in hostel_region or hostel_region in location):
            add(25, f"located in {hostel['region']}, matching your requested region")
        elif location in hostel_country or (hostel_country and hostel_country in location):
            add(15, f"located in {hostel['country']}, matching your requested location")
        else:
            nearby_towns = [t.lower() for t in hostel.get("location", {}).get("nearby_towns", [])]
            matched_nearby = [t for t in nearby_towns if location in t or t in location]
            if matched_nearby:
                add(22, f"close to {matched_nearby[0].title()}, near your requested location")
            elif location in hostel_continents(hostel):
                # weakest location signal — a continent match, e.g. "Europe"
                add(10, f"located in {hostel['country']}, within your requested continent ({location.title()})")

    # --- 2. Budget match ---
    budget_max = intent.get("budget_max")
    budget_flexibility = intent.get("budget_flexibility", "strict")  # "strict" or "approximate"
    if budget_max:
        price_range = hostel.get("price_range_usd")
        if price_range and price_range.get("min") is not None:
            cheapest_bed = price_range["min"]

            if budget_flexibility == "approximate":
                # "Around $10" is not the same claim as "under $10". The traveler
                # is naming a rough target, not a hard ceiling — and critically,
                # they don't care whether it's $6 or $10, only that it's roughly
                # in that zone. So: flat, EQUAL credit anywhere inside the zone
                # (no bonus for being cheaper within it — that would silently
                # reintroduce the same "price dominates ranking" problem this
                # whole feature exists to avoid), a real but gentler penalty
                # outside it, since "around" already implies some give.
                tolerance_ceiling = budget_max * 1.2  # 20% over is still "around"
                if cheapest_bed <= tolerance_ceiling:
                    add(20, f"${cheapest_bed}/night is close to your ~${budget_max} target")
                else:
                    add(-8, f"${cheapest_bed}/night is meaningfully above your ~${budget_max} target")
            else:
                # "strict" — under/no more than/max $X. A real ceiling.
                if cheapest_bed <= budget_max:
                    add(20, f"cheapest bed (${cheapest_bed}) fits your ${budget_max} budget")
                else:
                    add(-15, f"cheapest bed (${cheapest_bed}) is over your ${budget_max} budget")
        else:
            # We don't actually know this hostel's price. Don't silently
            # treat that as neutral — the traveler explicitly asked about
            # budget, so say so plainly rather than going quiet on it.
            add(0, f"price not listed in our data — could not confirm this fits your ${budget_max} budget, check the listing directly")
    else:
        # No specific number was given, but the traveler may still have expressed
        # budget-consciousness qualitatively ("cheap", "affordable", "budget hostel")
        # without a parseable number.
        BUDGET_SIGNAL_WORDS = ("budget", "cheap", "affordable", "inexpensive")
        expressed_budget_conscious = (
            any(any(w in vt.lower() for w in BUDGET_SIGNAL_WORDS) for vt in intent.get("vibe_tags", []))
            or any(any(w in tp.lower() for w in BUDGET_SIGNAL_WORDS) for tp in intent.get("traveler_profile", []))
        )
        if expressed_budget_conscious:
            price_range = hostel.get("price_range_usd")
            if price_range and price_range.get("min") is not None:
                cheapest_bed = price_range["min"]

                if local_price_bounds and local_price_bounds[1] > local_price_bounds[0]:
                    # PRIMARY: relative scoring against the actual candidate pool.
                    # 1.0 = cheapest option in this search, 0.0 = priciest.
                    local_min, local_max = local_price_bounds
                    relative_cheapness = (local_max - cheapest_bed) / (local_max - local_min)
                    relative_cheapness = max(0.0, min(1.0, relative_cheapness))
                    bonus = round(relative_cheapness * 30)
                    add(bonus, f"${cheapest_bed}/night — among the more budget-friendly options for this search (local range ${local_min}-${local_max})")
                else:
                    # FALLBACK: can't compute a distribution (e.g. only one priced
                    # candidate, or every candidate has the same price). Fall back
                    # to fixed dollar thresholds so budget-consciousness still
                    # counts for something rather than silently doing nothing.
                    ABSOLUTE_BUDGET_SCORE = {
                        1: 30, 2: 25, 3: 22, 4: 20, 5: 18, 6: 16, 7: 14,
                        8: 12, 9: 10, 10: 8, 11: 6, 12: 4, 13: 2,
                    }
                    bonus = ABSOLUTE_BUDGET_SCORE.get(cheapest_bed, 0 if cheapest_bed >= 14 else 30)
                    if bonus:
                        add(bonus, f"${cheapest_bed}/night, a genuinely budget-friendly price point")

    # --- 3. Vibe tag overlap ---
    vibe_tags = set(t.lower() for t in intent.get("vibe_tags", []))
    hostel_tags = set(t.lower() for t in hostel.get("vibe_tags", []))
    matched_tags = vibe_tags & hostel_tags
    if matched_tags:
        add(10 * len(matched_tags), f"matches your vibe: {', '.join(sorted(matched_tags))}")

    # Also check partial/substring matches (vibe_tags are often multi-word)
    # IMPORTANT: guard against negation prefixes (not_, non_, no_, anti_) —
    # naive substring matching would otherwise score "social" as a match
    # against "not_social", which is the exact opposite of what it means.
    # Also normalize hyphens to underscores first — Claude sometimes writes
    # "non-party" instead of "non_party", and a hyphenated negation should
    # be caught exactly the same way an underscored one is.
    NEGATION_PREFIXES = ("not_", "non_", "no_", "anti_")

    def is_negated(tag: str) -> bool:
        normalized = tag.replace("-", "_")
        return any(normalized.startswith(p) for p in NEGATION_PREFIXES)

    for vt in vibe_tags:
        for ht in hostel_tags:
            if vt == ht:
                continue  # already handled by the exact-match block above
            ht_is_negated = is_negated(ht)
            vt_is_negated = is_negated(vt)
            # strip prefix for the actual comparison so "not_social" vs "social" is checked properly
            ht_norm = ht.replace("-", "_")
            vt_norm = vt.replace("-", "_")
            ht_core = ht_norm.split("_", 1)[1] if ht_is_negated and "_" in ht_norm else ht
            vt_core = vt_norm.split("_", 1)[1] if vt_is_negated and "_" in vt_norm else vt

            if vt_core in ht_core or ht_core in vt_core:
                if ht_is_negated != vt_is_negated:
                    # one is negated and the other isn't, but the core concept matches
                    # -> this is a genuine CONFLICT, not a match. Penalize it.
                    add(-8, f"conflicting vibe: you want '{vt}' but this hostel is tagged '{ht}'")
                else:
                    # both positive, or both negated the same way -> genuine partial match
                    add(4, f"related vibe match: '{vt}' ~ '{ht}'")

    # --- 4. Traveler profile overlap ---
    traveler_profile = set(t.lower() for t in intent.get("traveler_profile", []))
    guest_type = set(t.lower() for t in hostel.get("social_vibe", {}).get("guest_type", []))
    matched_profile = traveler_profile & guest_type
    if matched_profile:
        add(8 * len(matched_profile), f"popular with travelers like you: {', '.join(sorted(matched_profile))}")

    # Partial match fallback — catches singular/plural mismatches like
    # "party_traveler" (intent parser) vs "party_travelers" (guest_type
    # vocabulary). These vocabularies were built at different points in
    # the project and drifted slightly; rather than rewrite either one,
    # partial matching (same approach as vibe_tags) closes the gap safely.
    already_matched = matched_profile
    for tp in traveler_profile - already_matched:
        for gt in guest_type - already_matched:
            tp_core = tp.rstrip("s")
            gt_core = gt.rstrip("s")
            if tp_core == gt_core or tp_core in gt_core or gt_core in tp_core:
                add(5, f"popular with travelers like you: {gt} (close match to '{tp}')")

    # --- 5. Stay duration signal ---
    stay_signal = intent.get("stay_duration_signal")
    if stay_signal == "long_term":
        if hostel.get("social_vibe", {}).get("good_for_remote_work"):
            add(6, "good for remote work / longer stays")
        if "long_term_traveler" in guest_type or "long_term_visa_stayers" in guest_type:
            add(6, "popular with long-term travelers")
    elif stay_signal == "short_term":
        if "transit_traveler" in guest_type:
            add(6, "well suited for a short transit stay")

    # --- 6. Transit access (uses the structured near_metro field, not just text tags) ---
    # Query wording varies ("near a train station", "close to metro", "good transport
    # links") but all point at the same structured fact we already collect per hostel.
    TRANSIT_KEYWORDS = ("train", "metro", "station", "transport", "subway", "transit")
    query_mentions_transit = any(
        any(kw in vt.lower() for kw in TRANSIT_KEYWORDS) for vt in vibe_tags
    )
    if query_mentions_transit:
        if hostel.get("location", {}).get("near_metro"):
            add(12, "near public transport (metro/train), matching your transit preference")
        if hostel.get("location", {}).get("near_airport"):
            add(4, "also close to the airport")

    # --- 7. Remote work vibe tags (query might say "digital nomad friendly" as a
    # vibe_tag rather than only via traveler_profile — check both places) ---
    REMOTE_WORK_KEYWORDS = ("remote work", "digital nomad", "coworking", "work friendly", "wifi")
    query_mentions_remote_work = any(
        any(kw in vt.lower() for kw in REMOTE_WORK_KEYWORDS) for vt in vibe_tags
    )
    if query_mentions_remote_work and hostel.get("social_vibe", {}).get("good_for_remote_work"):
        add(10, "confirmed good for remote work")

    # --- 8. Party level preference (structured field + ordinal-distance scoring) ---
    # A keyword list on the query side (e.g. "peaceful", "non-party") can never
    # enumerate every way Claude might phrase "I don't want a party hostel" —
    # softer phrasing like "not much a party place" or "priority is calmness"
    # can slip through undetected. The robust fix is the same pattern used for
    # budget_flexibility: have Claude classify intent into a small structured
    # field directly, then do graded (not binary) scoring against it.
    #
    # IMPORTANT DESIGN POINT: the true ideal for "avoid" and "prefer_quiet" is
    # a virtual target of 0 — BELOW "low" — not "low" itself. Our 5-point
    # scale starts at low=1 because we don't track a true "zero party"
    # category, but that doesn't mean "low" should be treated as a perfect
    # match: a low-party hostel still has some social/party element, and a
    # traveler who says "avoid" wants less than that. Using target=0 means
    # "low" always scores as "closest available, not perfect" for both
    # preferences, and steepness alone controls how forgiving each is of
    # drifting further away from that ideal. Mirrored on the high end:
    # "prefer_social"/"prefer_party" target 6 — one step ABOVE "high" — for
    # the same reason, so "high" is never treated as an unbeatable maximum.
    PARTY_LEVEL_SCALE = {"low": 1, "low_to_medium": 2, "medium": 3, "medium_to_high": 4, "high": 5}
    PARTY_PREFERENCE_CONFIG = {
        "avoid":         {"target": 0, "steepness": 15},
        "prefer_quiet":  {"target": 0, "steepness": 7},
        "neutral":       None,
        "prefer_social": {"target": 6, "steepness": 7},
        "prefer_party":  {"target": 6, "steepness": 15},
    }

    party_preference = intent.get("party_preference")
    config = PARTY_PREFERENCE_CONFIG.get(party_preference) if party_preference else None
    if config is not None:
        target = config["target"]
        steepness = config["steepness"]
        hostel_party_level = (hostel.get("social_vibe", {}).get("party_level") or "").lower()
        hostel_level_num = PARTY_LEVEL_SCALE.get(hostel_party_level)
        if hostel_level_num is not None:
            distance = abs(target - hostel_level_num)
            bonus = 20 - (distance * steepness)
            if distance == 0:
                add(bonus, f"party vibe ({hostel_party_level}) matches your preference perfectly")
            elif bonus > 0:
                add(bonus, f"party vibe ({hostel_party_level}) is reasonably close to your preference")
            else:
                add(bonus, f"heads up: party vibe ({hostel_party_level}) doesn't closely match your stated preference")
        else:
            # We asked about party level but don't actually know this
            # hostel's — say so rather than silently skip it, same
            # transparency principle as the missing-price case earlier.
            add(0, "party level not specified for this hostel — could not confirm how well it matches your social/quiet preference")

    # --- 9. Semantic vibe similarity (LLM-written profile <-> Voyage embeddings) ---
    # Complements the exact/partial vibe_tags matching above (#3): tags catch
    # explicit keyword overlap, this catches nuance a tag vocabulary can't
    # enumerate (e.g. "somewhere I can focus in the mornings but still meet
    # people at night" has no single matching tag, but embeds close to
    # hostels whose vibe_profile actually describes that balance).
    if semantic_entry:
        add(semantic_entry["points"], semantic_entry["reason"])

    total_score = sum(entry["points"] for entry in breakdown)
    return {"score": total_score, "breakdown": breakdown}


# Max points the semantic-similarity bonus can contribute to a single
# hostel's score. Kept modest relative to location (30) and budget (30) so
# it acts as a nuance layer on top of the existing signals, not a
# replacement for them — deliberately tunable, see Task #6 (validation
# against known tech-debt cases) before this weight is considered final.
MAX_SEMANTIC_POINTS = 15


def compute_semantic_entries(hostels: list, raw_query: str, hostel_embeddings: dict = None) -> dict:
    """
    Returns {hostel_id: {"points": int, "reason": str}} for hostels in the
    given (already location-filtered) candidate pool that have a
    precomputed vibe_profile embedding, using RELATIVE normalization
    within this candidate pool — the single best semantic match in the
    pool gets close to MAX_SEMANTIC_POINTS, the worst gets close to 0.

    This mirrors the relative-cheapness pattern already used for
    budget-conscious scoring above (see score_hostel, step 2): cosine
    similarity from Voyage's query/document embeddings doesn't have a
    fixed, universally-meaningful absolute scale (empirically, relevant
    query<->document pairs in this dataset land somewhere around 0.5-0.6,
    but that's not a documented guarantee), so ranking relative to what's
    actually in the current search is more robust than picking a magic
    absolute threshold.

    KNOWN LIMITATION (same tradeoff already accepted for relative
    cheapness): because normalization is relative to the current pool,
    the single best match always gets close to full credit even if
    nothing in that location is a great vibe fit, and the worst gets
    ~0 even if it's a decent fit. A future improvement could calibrate
    against a fixed reference distribution instead of pool-relative
    min/max. Tracked for revisit alongside Task #6.

    Degrades gracefully to {} (no semantic scoring, rest of matching
    proceeds normally) if: no raw_query was given, hostel_embeddings.json
    doesn't exist yet, or the live Voyage query-embedding call fails for
    any reason (network, missing/invalid API key, rate limit, etc.).
    Semantic matching is a bonus layer, not a hard dependency — it should
    never be able to take down search.
    """
    if not raw_query:
        return {}

    if hostel_embeddings is None:
        try:
            from semantic_similarity import load_hostel_embeddings
            hostel_embeddings = load_hostel_embeddings()
        except Exception:
            return {}

    try:
        from semantic_similarity import embed_query, cosine_similarity
        query_vec = embed_query(raw_query)
    except Exception:
        return {}

    similarities = {}
    for h in hostels:
        vec = hostel_embeddings.get(h["id"])
        if vec is not None:
            similarities[h["id"]] = cosine_similarity(query_vec, vec)

    if not similarities:
        return {}

    sim_min = min(similarities.values())
    sim_max = max(similarities.values())
    spread = sim_max - sim_min

    entries = {}
    for hostel_id, sim in similarities.items():
        relative = ((sim - sim_min) / spread) if spread > 0 else 1.0
        points = round(relative * MAX_SEMANTIC_POINTS)
        if points > 0:
            entries[hostel_id] = {
                "points": points,
                "reason": f"vibe profile semantically matches how you described what you're looking for (similarity {sim:.2f})",
            }
    return entries


def match_hostels(intent: dict, hostels: list, top_n: int = 10, raw_query: str = None, hostel_embeddings: dict = None) -> dict:
    """
    STEP 1 — Hard filter: if a location was specified, only consider
    hostels that are actually in that city/region/country. Location is
    a "must match" filter, not a ranking signal — it should never lose
    to a strong vibe/budget match from the wrong place.

    STEP 2 — Soft ranking: among the location-filtered hostels (or all
    hostels, if no location was given), score by budget/vibe/profile
    and sort descending.

    raw_query: the traveler's original free-text search string (before
    Claude's intent parsing). Optional — pass it to enable semantic vibe
    matching (see compute_semantic_entries). Omit it (e.g. in tests, or
    the __main__ block below) and matching falls back to the original
    structured-fields-only scoring, unchanged.

    hostel_embeddings: optional pre-loaded {hostel_id: vector} dict (see
    semantic_similarity.load_hostel_embeddings). Pass this in from the
    caller (e.g. loaded once at FastAPI startup, like HOSTELS itself) to
    avoid re-reading hostel_embeddings.json from disk on every request.
    If omitted, it's loaded lazily on first use.

    Returns a dict: {
        "total_matches": int,   # how many hostels scored > 0, before truncation
        "results": [...]        # top_n of them, in ranked order
    }
    """
    location = (intent.get("location") or "").lower()

    if location:
        filtered = []
        for h in hostels:
            hostel_city = (h.get("city") or "").lower()
            hostel_region = (h.get("region") or "").lower()
            hostel_country = (h.get("country") or "").lower()
            nearby_towns = [t.lower() for t in h.get("location", {}).get("nearby_towns", [])]
            if ((location in hostel_city or (hostel_city and hostel_city in location))
                    or (location in hostel_region or (hostel_region and hostel_region in location))
                    or (location in hostel_country or (hostel_country and hostel_country in location))
                    or any(location in nt or nt in location for nt in nearby_towns)
                    or location in hostel_continents(h)):
                filtered.append(h)
        hostels = filtered

    # Compute the actual price spread of THIS candidate pool (whatever
    # geographic grain was searched — city/region/country/continent/all),
    # so "cheap" can be scored relative to what's really on offer here,
    # not a fixed global dollar amount. See score_hostel() docstring.
    candidate_price_mins = [
        h["price_range_usd"]["min"] for h in hostels
        if h.get("price_range_usd") and h["price_range_usd"].get("min") is not None
    ]
    local_price_bounds = (min(candidate_price_mins), max(candidate_price_mins)) if candidate_price_mins else None

    # Semantic entries are computed ONCE for the whole candidate pool (one
    # Voyage API call for the query embedding, not one per hostel), then
    # looked up per-hostel inside the scoring loop below. See
    # compute_semantic_entries() for the relative-normalization approach
    # and its known limitation.
    semantic_entries = compute_semantic_entries(hostels, raw_query, hostel_embeddings) if raw_query else {}

    all_results = []
    for hostel in hostels:
        result = score_hostel(hostel, intent, local_price_bounds, semantic_entries.get(hostel["id"]))
        if result["score"] > 0:  # drop zero/negative matches entirely
            all_results.append({
                "id": hostel["id"],
                "name": hostel["name"],
                "city": hostel["city"],
                "country": hostel["country"],
                "score": result["score"],
                "breakdown": result["breakdown"],
                "price_range_usd": hostel.get("price_range_usd"),
            })

    all_results.sort(key=lambda r: r["score"], reverse=True)

    return {
        "total_matches": len(all_results),
        "results": all_results[:top_n],
    }


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

    outcome = match_hostels(test_intent, hostels)

    print(f"Total matches: {outcome['total_matches']} (showing top {len(outcome['results'])})\n")
    for m in outcome["results"]:
        print(f"[{m['score']}] {m['name']} ({m['city']}, {m['country']})")
        for entry in m["breakdown"]:
            sign = "+" if entry["points"] >= 0 else ""
            print(f"    {sign}{entry['points']:>3}  {entry['reason']}")
        print()
