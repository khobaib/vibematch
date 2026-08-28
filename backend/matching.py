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


def score_hostel(hostel: dict, intent: dict, local_price_bounds: tuple = None, semantic_entry: dict = None, raw_query: str = None) -> dict:
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

    # Combined searchable text for the new services-field keyword checks
    # (steps 12-16 below): the parsed vibe_tags ALONE aren't reliable for
    # these, because Claude's intent parser paraphrases rather than
    # preserving literal wording — e.g. "secure lockers" in a real query
    # came back as just the tag "secure" (no "locker" anywhere), and "hair
    # dryer... dry my clothes" came back as "practical amenities"/"laundry"
    # (no "hair dryer" or "drying" anywhere). Confirmed directly via
    # validate_semantic_matching.py: both bonuses silently failed to fire
    # despite the traveler explicitly asking for both. Paraphrase-tolerant
    # tag matching is fine for fuzzy vibe language, but actively wrong for
    # specific factual asks like this, where the literal word is what
    # matters. Falling back to the raw query text (when available) fixes
    # it without weakening the existing vibe_tags-based steps elsewhere.
    query_search_text = " ".join(vibe_tags)
    if raw_query:
        query_search_text += " " + raw_query.lower()
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

    # --- 8. Party level preference (structured field + explicit per-preference score table) ---
    # A keyword list on the query side (e.g. "peaceful", "non-party") can never
    # enumerate every way Claude might phrase "I don't want a party hostel" —
    # softer phrasing like "not much a party place" or "priority is calmness"
    # can slip through undetected. The robust fix is the same pattern used for
    # budget_flexibility: have Claude classify intent into a small structured
    # field directly, then do graded (not binary) scoring against it.
    #
    # HISTORY / WHY THIS IS A TABLE, NOT A FORMULA: earlier versions used a
    # single distance x steepness formula against a virtual target below the
    # scale's floor (since party_level had no true "zero" category — "low"
    # was the lowest value that existed). Direct product review surfaced two
    # real problems with that: (1) party_level's real-world floor conflated
    # two genuinely different things — a hostel with truly NO social/party
    # element, vs. one with occasional light activity — and a traveler who
    # says "avoid party" wants the former, not "the closest available
    # option, mildly rewarded" (which the old formula gave "low": +5). (2) a
    # single formula can't express asymmetric curve shapes for different
    # strictness levels ("avoid" should punish "low" hard; "prefer_quiet"
    # should barely penalize it) without genuinely different math per case,
    # which a table expresses directly and a shared formula can't. Fixed by
    # adding a real "none" tier to party_level (see
    # reclassify_party_level.py — 13 of 49 "low"-tagged hostels were
    # reclassified to "none" using their own existing review/vibe data, 36
    # correctly stayed "low"), and replacing the formula with this explicit,
    # hand-tuned table (values set via direct product discussion, not
    # derived from a formula — see DECISIONS_LOG.md for the full reasoning).
    #
    # This also depends on match_hostels() no longer dropping score <= 0
    # results entirely (see that function's docstring) — that's what makes
    # it safe to score "avoid" + "high" as sharply negative (-50) without
    # risking an empty result set: a badly-scoring hostel now just ranks
    # near the bottom instead of vanishing.
    PARTY_LEVEL_SCALE = {"none": 0, "low": 1, "low_to_medium": 2, "medium": 3, "medium_to_high": 4, "high": 5}
    PARTY_SCORE_TABLE = {
        # Strict "avoid party/noise" — ideal is genuinely no social element;
        # even "low" (some light activity) is a real miss, not a near-match.
        "avoid":         {"none": 20, "low": -10, "low_to_medium": -20, "medium": -30, "medium_to_high": -40, "high": -50},
        # Softer "no party preferred" — still wants quiet, but "low" is a
        # genuinely acceptable outcome (occasional light activity is fine),
        # just not the ideal.
        "prefer_quiet":  {"none": 10, "low": 0, "low_to_medium": -5, "medium": -10, "medium_to_high": -15, "high": -20},
        "neutral":       None,
        # Mirror image of prefer_quiet: "high" is ideal, "medium_to_high" is
        # genuinely fine, quieter levels are increasingly a miss.
        "prefer_social": {"none": -20, "low": -15, "low_to_medium": -10, "medium": -5, "medium_to_high": 0, "high": 10},
        # Mirror image of avoid: "high" is the strict ideal, anything short
        # of that is a real miss for someone who explicitly wants the party.
        "prefer_party":  {"none": -50, "low": -40, "low_to_medium": -30, "medium": -20, "medium_to_high": -10, "high": 20},
    }

    # DAYTIME/EVENING SPLIT (Fix B for the "focus during the day, meet people
    # over dinner" dual-mode gap — see DECISIONS_LOG.md). A single
    # `party_preference` value can't express "quiet mornings, social
    # evenings" — it forces a blended read that penalizes exactly the
    # hostels that would be the best fit (real example: a hostel with
    # good_for_remote_work + party_level "low_to_medium" + real evening
    # activities scored WORSE under prefer_social's blended table than a
    # pure high-party hostel with zero daytime-focus signal). Fixed at the
    # INTENT level by parsing two additional optional fields
    # (daytime_vibe_preference / evening_vibe_preference), only set by the
    # parser when a query genuinely names two different times of day with
    # two different vibes — see main.py's parse_intent prompt.
    #
    # EXPERIMENTAL / KNOWN LIMITATION: this only half-solves the problem.
    # The hostel side still only has ONE `party_level` for the whole
    # property — there's no real `daytime_party_level`/`evening_party_level`
    # data yet (that needs genuine new research, tracked in the Field/
    # Feature Backlog). So this branch reads from those two hostel fields,
    # which are null for every real hostel in hostels.json right now — on
    # real data this whole branch currently falls through to "not specified"
    # for every hostel. It's only exercised meaningfully against
    # test_fixtures/synthetic_daynight_test.json (clearly-fake, randomly
    # generated values used ONLY by validate_daynight_split.py, never
    # merged into hostels.json), specifically to mechanically prove the
    # split-scoring logic itself works correctly before the real research
    # is done. Do not mistake a null result here for "confirmed no split
    # preference exists" — it currently just means we haven't researched it.
    daytime_pref = intent.get("daytime_vibe_preference")
    evening_pref = intent.get("evening_vibe_preference")
    is_day_night_split_query = bool(daytime_pref or evening_pref)

    # Halved version of the prefer_quiet/prefer_social tables above — used
    # TWICE (once for daytime, once for evening) on a split query, so each
    # half is scaled down to keep the combined total comparable to the
    # single-mode step below rather than double-counting.
    SPLIT_PARTY_SCORE_TABLE = {
        "quiet": {k: round(v / 2) for k, v in PARTY_SCORE_TABLE["prefer_quiet"].items()},
        "social": {k: round(v / 2) for k, v in PARTY_SCORE_TABLE["prefer_social"].items()},
    }

    def score_split_period(period_name, preference, hostel_level_field):
        if not preference:
            return
        score_table = SPLIT_PARTY_SCORE_TABLE.get(preference)
        if score_table is None:
            return
        hostel_level = (hostel.get("social_vibe", {}).get(hostel_level_field) or "").lower()
        if hostel_level in score_table:
            bonus = score_table[hostel_level]
            if bonus == max(score_table.values()):
                add(bonus, f"{period_name} vibe ({hostel_level}) matches your {period_name} preference well")
            elif bonus > 0:
                add(bonus, f"{period_name} vibe ({hostel_level}) is reasonably close to your {period_name} preference")
            else:
                add(bonus, f"heads up: {period_name} vibe ({hostel_level}) doesn't closely match your {period_name} preference")
        else:
            add(0, f"{period_name}-specific party level not researched for this hostel yet — could not confirm how well it matches your {period_name} preference")

    if is_day_night_split_query:
        score_split_period("daytime", daytime_pref, "daytime_party_level")
        score_split_period("evening", evening_pref, "evening_party_level")
    else:
        # --- 8. Party level preference (single-mode fallback, unchanged) ---
        party_preference = intent.get("party_preference")
        score_table = PARTY_SCORE_TABLE.get(party_preference) if party_preference else None
        if score_table is not None:
            hostel_party_level = (hostel.get("social_vibe", {}).get("party_level") or "").lower()
            if hostel_party_level in score_table:
                bonus = score_table[hostel_party_level]
                if bonus == max(score_table.values()):
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

    # --- 9. Views (structured field, previously collected but never scored) ---
    # DECISIONS_LOG.md OPEN item resolved: the `views` field (has_view,
    # view_type, view_from) existed for 62 hostels with zero scoring logic
    # ever referencing it — a query about "ocean view" or "sound of waves"
    # could only match by coincidence via vibe_tags text overlap. Also
    # required normalize_views.py first: view_type/view_from were originally
    # free-text with no controlled vocabulary (inconsistent formatting,
    # multi-concept strings) — unreliable to match against directly. Both
    # fixed together; see DECISIONS_LOG.md for the full writeup.
    VIEW_TYPE_KEYWORDS = {
        "ocean": ("ocean", "sea view", "seaview", "beachfront", "wave", "coastal view"),
        "mountain": ("mountain", "himalay", "hill view", "alpine"),
        "lake": ("lake",),
        "river": ("river",),
        "valley": ("valley",),
        "city": ("city view", "cityscape", "skyline"),
        "garden": ("garden view",),
        "jungle": ("jungle view", "rainforest view", "forest view"),
        "pool": ("pool view",),
        "temple": ("temple view",),
        "cliff": ("cliff",),
        "rooftop_skyline": ("rooftop view",),
        "countryside": ("countryside view", "rural view", "farmland view"),
        "rice_paddy": ("rice paddy", "rice field"),
        "desert": ("desert view",),
        "park": ("park view",),
        "volcano": ("volcano",),
    }
    GENERIC_VIEW_KEYWORDS = ("view", "scenic", "overlooking", "vista")

    hostel_view_types = set(hostel.get("views", {}).get("view_type") or [])
    if hostel.get("views", {}).get("has_view") and hostel_view_types:
        # Specific-type match: query names a particular kind of view the hostel actually has.
        matched_types = set()
        for view_type, keywords in VIEW_TYPE_KEYWORDS.items():
            if view_type in hostel_view_types and any(
                any(kw in vt.lower() for kw in keywords) for vt in vibe_tags
            ):
                matched_types.add(view_type)

        if matched_types:
            types_str = ", ".join(sorted(matched_types))
            article = "an" if types_str[0].lower() in "aeiou" else "a"
            add(12 * len(matched_types), f"has {article} {types_str} view, matching what you're looking for")
        else:
            # Generic "I want a view" language, without naming a specific type —
            # still real credit, just less than a precise type match, and the
            # reason names the actual view(s) so it stays auditable/specific.
            query_mentions_view_generically = any(
                any(kw in vt.lower() for kw in GENERIC_VIEW_KEYWORDS) for vt in vibe_tags
            )
            if query_mentions_view_generically:
                add(6, f"has a view ({', '.join(sorted(hostel_view_types))}), matching your interest in a scenic stay")

    # --- 10. Nearby attractions (structured location.nearby field, restructured
    # from informal free-text via normalize_nearby_and_boutique.py — existed as
    # unstructured strings for 118 hostels and was never referenced in scoring;
    # the remaining 110 hostels have no nearby data at all yet, tracked as part
    # of the larger new-research data-enrichment pass). Matches a query naming
    # a category of nearby place (cafe, beach, nightlife, etc.) against the
    # hostel's actual nearby list, with extra credit when it's walkable. See
    # DECISIONS_LOG.md.
    NEARBY_TYPE_KEYWORDS = {
        "cafe": ("cafe", "coffee shop", "coffee"),
        "nature": ("nature", "hiking", "trekking", "trail", "forest walk", "national park"),
        "landmark": ("landmark", "temple", "monument", "historic site", "sightseeing"),
        "nightlife": ("nightlife", "bar", "bars", "club", "clubbing", "pub"),
        "beach": ("beach",),
        "viewpoint": ("viewpoint", "scenic spot", "lookout", "sunset spot"),
        "market": ("market", "bazaar", "night market"),
    }

    hostel_nearby = hostel.get("location", {}).get("nearby") or []
    if hostel_nearby and isinstance(hostel_nearby[0], dict):
        # Dedupe to the best (walkable if possible) match per place type, so
        # e.g. 3 separate cafes nearby doesn't triple-count the same signal.
        matched_nearby_types = {}
        for entry in hostel_nearby:
            place_type = entry.get("type")
            keywords = NEARBY_TYPE_KEYWORDS.get(place_type)
            if not keywords:
                continue
            if any(any(kw in vt.lower() for kw in keywords) for vt in vibe_tags):
                existing = matched_nearby_types.get(place_type)
                if existing is None or (entry.get("walkable") and not existing.get("walkable")):
                    matched_nearby_types[place_type] = entry

        for place_type, entry in matched_nearby_types.items():
            if entry.get("walkable"):
                add(10, f"walkable to {entry['name']} ({place_type}), matching what you're looking for nearby")
            else:
                add(6, f"has {entry['name']} ({place_type}) nearby, matching what you're looking for")

    # --- 11. Boutique style (new field, classified from existing
    # accommodation_type/vibe_tags/facilities/exclusive_features via
    # normalize_nearby_and_boutique.py — "boutique" is a style descriptor
    # that cuts across accommodation_type rather than being its own value,
    # so it's a separate boolean). See DECISIONS_LOG.md.
    BOUTIQUE_KEYWORDS = ("boutique", "design hostel", "design-focused", "stylish", "upscale", "aesthetic", "curated", "chic")
    query_mentions_boutique = (
        any(any(kw in vt.lower() for kw in BOUTIQUE_KEYWORDS) for vt in vibe_tags)
        or any(any(kw in tp.lower() for kw in BOUTIQUE_KEYWORDS) for tp in traveler_profile)
    )
    if query_mentions_boutique and hostel.get("is_boutique_style"):
        add(10, "boutique-style property, matching your preference for a more design-focused/upscale stay")

    # --- 12. Bed bug safety signal (services.bed_bug_reports) ---
    # Unlike the other new services-field steps below, this one applies
    # REGARDLESS of query wording — a credible bed bug report is a real
    # dealbreaker-class safety signal, not a mere preference, so it always
    # weighs into ranking rather than only showing up if the traveler
    # happened to ask about cleanliness. (The softer, keyword-gated bonus
    # for a confirmed-clean result still requires the traveler to have
    # actually raised a safety/cleanliness concern — a hostel doesn't get
    # bonus credit for something nobody asked about.) Data from the
    # bed-bug/lockers/hair-dryer/drying/curfew research pass — see
    # DECISIONS_LOG.md.
    bed_bug_reports = hostel.get("services", {}).get("bed_bug_reports")
    SAFETY_KEYWORDS = ("safe", "safety", "clean", "hygien", "bed bug", "pest", "comfort", "comfortable", "cozy")
    query_mentions_safety = any(kw in query_search_text for kw in SAFETY_KEYWORDS)
    if bed_bug_reports is True:
        add(-15, "reported bed bug complaints in reviews — worth checking recent listings before booking")
    elif bed_bug_reports is False and query_mentions_safety:
        add(6, "no credible bed bug reports found in reviews")

    # --- 13. Lockers / secure storage (services.lockers) ---
    LOCKER_KEYWORDS = ("locker", "secure storage", "storage", "safe box", "valuables", "security")
    query_mentions_lockers = any(kw in query_search_text for kw in LOCKER_KEYWORDS)
    if query_mentions_lockers:
        lockers = hostel.get("services", {}).get("lockers") or {}
        lockers_available = lockers.get("available")
        if lockers_available is True:
            locker_type = lockers.get("type")
            detail = f" ({locker_type})" if locker_type else ""
            add(8, f"has secure lockers{detail}, matching your interest in secure storage")
        elif lockers_available is False:
            add(-5, "no lockers confirmed — heads up if secure storage matters to you")

    # --- 14. Hair dryer availability (services.hair_dryer_available) ---
    HAIR_DRYER_KEYWORDS = ("hair dryer", "hairdryer", "blow dry", "blow-dry")
    query_mentions_hair_dryer = any(kw in query_search_text for kw in HAIR_DRYER_KEYWORDS)
    if query_mentions_hair_dryer:
        hair_dryer = hostel.get("services", {}).get("hair_dryer_available")
        if hair_dryer is True:
            add(6, "hair dryer available, matching what you asked about")
        elif hair_dryer is False:
            add(-4, "no hair dryer confirmed — heads up since you asked about this")

    # --- 15. Clothes drying facility (services.clothes_drying_facility) ---
    # Deliberately distinct from the existing laundry_service field — "can
    # I wash clothes" and "can I actually dry them" are different practical
    # questions, especially in humid climates.
    DRYING_KEYWORDS = ("dry clothes", "drying", "dryer", "dry my laundry", "line dry")
    query_mentions_drying = any(kw in query_search_text for kw in DRYING_KEYWORDS)
    if query_mentions_drying:
        drying = hostel.get("services", {}).get("clothes_drying_facility")
        if drying is True:
            add(6, "has a clothes-drying facility, matching what you asked about")
        elif drying is False:
            add(-4, "no clothes-drying facility confirmed — heads up since you asked about this")

    # --- 16. Curfew policy (services.curfew_policy) ---
    # Most travelers who bring this up are looking for FLEXIBILITY (no
    # curfew / 24hr access) rather than actively wanting a curfew, so query
    # mentions of curfew/late-access language are treated as "wants no
    # curfew" — the far more common real intent behind this kind of phrase.
    # A STRONG explicit ask ("24/7 access", "round the clock") signals a
    # much harder requirement than a soft mention of "curfew" alone — a
    # real curfew is a much bigger miss for that traveler, so it gets a
    # sharper penalty (-20 vs -8), per direct product correction.
    GENERAL_CURFEW_KEYWORDS = ("curfew", "24 hour reception", "24hr reception", "late night", "come back late", "flexible check-in", "no curfew")
    STRONG_CURFEW_KEYWORDS = ("24/7", "24-7", "24/7 access", "round the clock", "round-the-clock", "anytime access")
    query_mentions_strong_curfew = any(kw in query_search_text for kw in STRONG_CURFEW_KEYWORDS)
    query_mentions_curfew = query_mentions_strong_curfew or any(kw in query_search_text for kw in GENERAL_CURFEW_KEYWORDS)
    if query_mentions_curfew:
        curfew_policy_raw = hostel.get("services", {}).get("curfew_policy")
        curfew_policy = (curfew_policy_raw or "").lower()
        if curfew_policy:
            # The actual data phrases "no curfew" many different ways — "no
            # curfew", "no strict curfew", "no formal curfew", "no explicit
            # curfew", "no fixed curfew", "not a strict curfew", etc. A plain
            # substring check for the exact phrase "no curfew" missed most of
            # these (caught directly via testing — several genuinely
            # no-curfew hostels were about to be wrongly penalized as having
            # a real curfew). Use a regex that tolerates 0-2 words between
            # "no"/"not" and "curfew" instead of an exact-phrase match.
            import re
            has_no_curfew_language = bool(
                re.search(r"\bno\w*\s+(\w+\s+){0,2}curfew\b", curfew_policy)
            ) or any(p in curfew_policy for p in ("24hr", "24-hour", "24 hour"))
            has_real_curfew = "curfew" in curfew_policy and not has_no_curfew_language
            if has_no_curfew_language:
                add(8, "no curfew / 24hr access, matching your need for late-night flexibility")
            elif has_real_curfew:
                penalty = -20 if query_mentions_strong_curfew else -8
                add(penalty, f"heads up: this hostel has a curfew policy ({curfew_policy_raw}), which may not suit your need for late-night/24-7 access")

    # --- 17. Daytime work-focus combo (multi-field signal, not a single tag) ---
    # Direct product correction on the still-open "focus during the day, meet
    # people over dinner" dual-mode gap (DECISIONS_LOG.md): "work focus"
    # isn't one fact, it's a bundle — strong wifi, a calm/AC'd place to sit
    # with a laptop, coffee, easy commuting. We only actually HAVE structured
    # data for a fraction of that bundle (confirmed by checking the schema
    # directly): `good_for_remote_work` (already scored in step 7 above —
    # NOT repeated here, to avoid double-counting the same signal),
    # `near_metro`/`near_airport` (commute ease), and coffee AVAILABILITY
    # (not necessarily free — direct correction: "lobby/cafe offers some
    # coffee" means "is coffee available during work hours," not
    # specifically "is it free"). No dedicated "coffee available" field
    # exists, so this is approximated from three real signals that each
    # independently suggest coffee is available on-site: `free_tea_coffee`
    # (definitely available, and free), an on-site restaurant/bar
    # (`facilities.restaurant_onsite`/`bar_onsite` — these almost always
    # serve coffee even when it's not itemized as "free"), or the word
    # "cafe" appearing in the hostel's own `exclusive_features`/`vibe_tags`
    # (51/226 hostels). Wifi strength, desk/seating setup, and common-area
    # AC are NOT structured fields yet (only 11/226 hostels even mention
    # "wifi" anywhere in free text) — tracked in the Field/Feature Backlog
    # for a future research pass, not faked here. This step adds the
    # SUPPORTING signals on top of step 7's core bonus, so a query asking
    # about daytime focus gets credit for the fuller (if still partial)
    # picture rather than just the one good_for_remote_work flag.
    FOCUS_KEYWORDS = ("focus", "work during the day", "quiet during the day", "productive", "remote work", "digital nomad", "coworking", "co-working", "wifi", "laptop")
    query_mentions_focus = any(kw in query_search_text for kw in FOCUS_KEYWORDS)
    if query_mentions_focus:
        hostel_location = hostel.get("location", {})
        if hostel_location.get("near_metro") or hostel_location.get("near_airport"):
            add(4, "easy commute (near metro/airport) — useful if you need to step out during a work day")

        kitchen_food = hostel.get("kitchen_food", {})
        facilities = hostel.get("facilities", {})
        text_fields = " ".join(hostel.get("exclusive_features", []) + hostel.get("vibe_tags", [])).lower()
        if kitchen_food.get("free_tea_coffee"):
            add(3, "free tea/coffee available, handy for work sessions")
        elif facilities.get("restaurant_onsite") or facilities.get("bar_onsite"):
            add(3, "on-site restaurant/bar, likely a place to grab coffee during work hours")
        elif "cafe" in text_fields:
            add(3, "has an on-site cafe, handy for work sessions")

        lounge_ac = facilities.get("lounge_has_ac")
        if lounge_ac is True:
            add(3, "air-conditioned common area, more comfortable for daytime work")

        # wifi_quality / desk_setup (EXPERIMENTAL, see DECISIONS_LOG.md —
        # not real data yet for any hostel in hostels.json; only exercised
        # against test_fixtures/synthetic_backlog_fields_test.json via
        # validate_backlog_fields.py, same pattern as the daytime/evening
        # split fields above). Reading via .get() means this is a no-op on
        # every real hostel today (the keys simply aren't present) and
        # only activates once real per-hostel wifi/desk research exists.
        wifi_quality = facilities.get("wifi_quality")
        if wifi_quality in ("good", "excellent"):
            add(6, f"wifi reported {wifi_quality}, reliable for a work day")
        elif wifi_quality == "weak":
            add(-4, "wifi reported weak — heads up if you need it for work")
        elif wifi_quality == "none":
            add(-6, "no wifi confirmed — likely a poor fit for a work-focused stay")

        desk_setup = facilities.get("desk_setup")
        if desk_setup == "good":
            add(5, "has a proper desk/seating setup for laptop work")
        elif desk_setup == "basic":
            add(2, "has basic seating that could work for a laptop")
        elif desk_setup == "none":
            add(-3, "no dedicated workspace/desk confirmed")

    # --- 18. Evening social-mixing combo (multi-field signal, distinct from
    # the raw party-vibe match in step 8) ---
    # Direct product correction, same open item as above: "meet people over
    # dinner" isn't a party-hostel question — it's a probability question
    # about whether the *kind* of guests and the hostel's own organized
    # social activities make casual mixing likely, independent of nightlife
    # intensity. Built from existing structured fields: `guest_type` (solo-
    # heavy vs. group-heavy — group travelers tend to stick to their own
    # group rather than mixing with strangers), `social_activities` /
    # `weekend_activities` (organized activities create natural
    # opportunities to meet people), `staff.friendliness`, and a gentler
    # light-to-medium `party_level` read (some social energy without being
    # an overwhelming party scene). Extended below with three more
    # EXPERIMENTAL fields (communal_dinner_available, whatsapp_community_
    # group_available, solo_group_ratio) — same status as wifi_quality/
    # desk_setup above: real schema + real scoring logic, but no real
    # hostel currently has these fields populated; only exercised against
    # test_fixtures/synthetic_backlog_fields_test.json. Direct product input
    # on the WhatsApp field specifically: an active community group is a
    # genuinely strong, distinct signal — it's the actual mechanism by which
    # a hostel's guests coordinate hangouts/day-plans/group activities, AND
    # it's why travelers often return to the same hostel on a later trip
    # (they're still in the group) — weighted accordingly above the generic
    # "organizes activities" bonus.
    SOCIAL_MIXING_KEYWORDS = ("meet people", "meet new people", "meet other travelers", "meet fellow travelers", "make friends", "socialize", "socialise", "mingle", "connect with other travelers", "over dinner", "communal dinner", "shared meals", "whatsapp", "community group", "stay in touch", "keep in touch", "regulars")
    query_mentions_social_mixing = any(kw in query_search_text for kw in SOCIAL_MIXING_KEYWORDS)
    if query_mentions_social_mixing:
        social = hostel.get("social_vibe", {})
        guest_types = [g.lower() for g in social.get("guest_type", [])]

        # solo_group_ratio (EXPERIMENTAL — new, more granular field) takes
        # priority over the older guest_type text heuristic when present;
        # falls back to the original heuristic otherwise so real hostels
        # (which only have guest_type today) keep working unchanged.
        solo_group_ratio = social.get("solo_group_ratio")
        if solo_group_ratio == "mostly_solo":
            add(6, "guest mix is mostly solo travelers, good odds of meeting people to connect with")
        elif solo_group_ratio == "mixed":
            add(2, "guest mix is a blend of solo travelers and groups")
        elif solo_group_ratio == "mostly_groups":
            add(-6, "guest mix leans heavily toward groups, which can make it harder to naturally meet new people")
        else:
            if any("solo" in g for g in guest_types):
                add(5, "popular with solo travelers, good odds of meeting other solo travelers to connect with")
            if any("group" in g for g in guest_types):
                add(-5, "guests here tend to travel in groups, which can make it harder to naturally meet new people")

        activities = (social.get("social_activities") or []) + (social.get("weekend_activities") or [])
        if activities:
            example = activities[0]
            add(6, f"organizes social activities (e.g. {example}), which create natural chances to meet other travelers")

        if social.get("communal_dinner_available") is True:
            add(6, "hosts communal/family-style dinners, a natural way to meet other travelers over a meal")

        if social.get("whatsapp_community_group_available") is True:
            add(8, "has an active WhatsApp/community group — a strong signal of an ongoing social community, and often why travelers come back on a later trip")

        friendliness = (social.get("friendliness") or hostel.get("staff", {}).get("friendliness") or "").lower()
        if any(w in friendliness for w in ("friendly", "welcoming", "excellent", "warm")):
            add(3, "staff described as especially friendly, which tends to correlate with an easy, welcoming social atmosphere")

        hostel_party_level = (social.get("party_level") or "").lower()
        if hostel_party_level in ("low_to_medium", "medium"):
            add(4, "some social energy without being an overwhelming party scene — good odds of casual mixing like meeting people over dinner")

    # --- 19. Food self-sufficiency combo (free_breakfast is REAL data;
    # diy_breakfast_available and kitchen_utensils_quality are EXPERIMENTAL,
    # same status as the fields above — schema + scoring logic real, actual
    # values not researched yet, only exercised via the synthetic fixture) ---
    BREAKFAST_KEYWORDS = ("breakfast", "diy breakfast", "self-serve breakfast", "make my own breakfast", "bread and jam", "cook my own food", "self-catering", "kitchen utensils", "pots and pans", "cook my own meals")
    query_mentions_breakfast = any(kw in query_search_text for kw in BREAKFAST_KEYWORDS)
    if query_mentions_breakfast:
        kitchen_food = hostel.get("kitchen_food", {})
        if kitchen_food.get("free_breakfast") is True:
            add(8, "free breakfast included")
        elif kitchen_food.get("diy_breakfast_available") is True:
            add(5, "offers DIY breakfast basics (bread/jam/butter/tea) so you can put together your own breakfast")

        kitchen_utensils_quality = kitchen_food.get("kitchen_utensils_quality")
        if kitchen_utensils_quality == "good":
            add(5, "well-stocked kitchen utensils, good for cooking your own meals")
        elif kitchen_utensils_quality == "basic":
            add(2, "basic kitchen utensils available")
        elif kitchen_utensils_quality == "none":
            add(-3, "no real kitchen utensils confirmed, even if a kitchen space exists")

    # --- 20. Semantic vibe similarity (LLM-written profile <-> Voyage embeddings) ---
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

    # DESIGN NOTE (changed after direct product review — see DECISIONS_LOG.md):
    # previously any hostel scoring <= 0 was dropped ENTIRELY, not just
    # ranked low. That was a real problem: a traveler who explicitly said
    # "avoid party" deserved to see the closest available options even if
    # every candidate has some social element and scores negative — showing
    # nothing is worse than honestly showing "here's the best we've got,
    # though nothing here is a great fit." It also forced party-preference
    # scoring to stay artificially gentle (see score_hostel step 8) purely
    # to avoid the empty-results risk, which is the wrong reason to soften a
    # score.
    #
    # Now: a hostel is only excluded if it has NO breakdown entries at all
    # (i.e. nothing about the search criteria applied to it whatsoever —
    # e.g. a broad, unconstrained query against a hostel with no location
    # match and no vibe/profile overlap). Anything that was genuinely
    # evaluated against the traveler's criteria is shown, regardless of
    # whether the net score came out negative — ranking (not gating) is
    # what handles quality now. `is_recommended` marks the score > 0 line so
    # callers (frontend, AI explanation) can still distinguish "a real
    # match" from "the least-bad option we had," rather than presenting a
    # negative-scoring result with the same confidence as a strong one.
    all_results = []
    genuine_match_count = 0
    for hostel in hostels:
        result = score_hostel(hostel, intent, local_price_bounds, semantic_entries.get(hostel["id"]), raw_query)
        if not result["breakdown"]:  # nothing about this hostel was actually evaluated — no signal to show
            continue
        if result["score"] > 0:
            genuine_match_count += 1
        all_results.append({
            "id": hostel["id"],
            "name": hostel["name"],
            "city": hostel["city"],
            "country": hostel["country"],
            "score": result["score"],
            "is_recommended": result["score"] > 0,
            "breakdown": result["breakdown"],
            "price_range_usd": hostel.get("price_range_usd"),
        })

    all_results.sort(key=lambda r: r["score"], reverse=True)

    return {
        # "total_matches" keeps its original meaning — genuine (score > 0)
        # matches — so existing callers/tests that treat this as "how many
        # real hits were there" aren't silently redefined. "results" below
        # can still include more than this many entries (up to top_n),
        # since it now also surfaces the closest available non-matches.
        "total_matches": genuine_match_count,
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
