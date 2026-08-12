# VibeMatch — Decisions & Tech Debt Log

*A running record of product/technical decisions and known shortcuts, kept during early-stage
development ahead of a formal PRD. Organized so it can be merged into a PRD later — each entry
has the decision, the reasoning, and the date/context it was made in.*

---

## How to Use This Doc

- **Decisions** = choices we made deliberately, with reasoning, that we're standing behind for now
- **Tech Debt** = known shortcuts or limitations we accepted on purpose, with a plan to revisit
- Nothing here is final — this is a log of *current* thinking, not commitments carved in stone

---

## Product Decisions

### Positioning: Discovery layer, not a booking platform
VibeMatch sits on top of existing booking platforms (Hostelworld, Booking.com) rather than
competing with their inventory/booking infrastructure. Users search conversationally, get ranked
results with explanations, then click out to book on the partner site (affiliate revenue model).
**Why:** Building booking infrastructure from scratch is a much bigger lift than building a smarter
discovery/matching layer, and doesn't play to the actual differentiator (intent understanding).

### MVP target segment: solo backpackers / hostels
**Why:** This is the founder's own deep, lived domain expertise (50+ personally visited
hostels), making it the strongest possible foundation for both data quality and product
intuition. Other accommodation types (hotels, villas) are tracked in the schema but not the
primary design target yet.

### Budget is a soft signal, not a hard filter
An over-budget hostel still appears in results, ranked lower — not excluded entirely.
**Why:** Real travelers often flex on budget for the right match; hard-excluding an $18/night
option from someone with a $15 budget could hide their actual best fit. Decided explicitly
when building the matching engine (see Technical Decisions below).

### Location is a hard filter, not a soft signal
If a location is specified, hostels outside it are excluded before scoring even runs.
**Why:** Unlike budget, location has no "flex" — a Cambodia hostel is never useful to someone
searching for Goa, no matter how well it scores on vibe or budget. (This was a real bug we
found and fixed — see Tech Debt / Resolved Issues below.)

---

## Technical Decisions

### Stack: FastAPI + Python backend, React + Vite frontend
**Why:** FastAPI/Python matches existing backend engineering background (fast to build in,
native async support for LLM API calls). React was a deliberate learning goal alongside the
build — chosen despite being new territory because of its relevance to the target job market.

### Data storage: JSON file now, PostgreSQL later
**Why:** At ~66 hostels, a JSON file is simpler to hand-edit and version-control than standing
up a database. Migration path to Postgres is planned once the dataset or write-concurrency
needs outgrow a flat file (see roadmap Phase 4).

### Intent parser: iterative, rule-taught prompt engineering
The Claude prompt explicitly teaches inference rules (e.g. "mentions of local market + metro
access together → long_term_traveler") rather than relying on generic instructions.
**Why:** Early testing showed generic prompts produced shallow traveler_profile output (e.g.
just `["solo", "backpacker"]`). Explicitly encoding the founder's own travel-pattern knowledge
into the prompt produced dramatically richer, more accurate inferences — validated by
before/after comparison on real queries.

### Model choice: Claude Sonnet 5 (switched from Sonnet 4.6)
**Why:** At time of switching, Sonnet 5 was both more capable and priced lower than 4.6 due to
introductory pricing. Revisit if pricing/model landscape changes.

### Matching engine: additive point-based scoring, not ML-based
Each signal (location, budget, vibe tags, traveler profile, stay duration) adds/subtracts
points; results sort by total score. Every point addition records a human-readable "reason."
**Why:** Transparent and debuggable — every score can be explained by reading the reasons list,
which also becomes the raw material for the planned "Why we matched this" feature. An ML-based
ranker would be a black box at this stage, with no training data to justify the complexity yet.

---

## Data Decisions

### Two-tier research depth: deep-dive for personal/testing-critical hostels, lighter-touch for broad diversity batches
Formalizing a pattern used three times now (a 50-hostel diversity batch, a 10-hostel Southeast
Asia batch, and a 60-hostel Europe/Australia/South America batch): personally-visited hostels and
ones added to fix a specific tested gap (e.g. the Bangkok party hostel fix) get full multi-source
research per property. Large-scale geographic diversity batches instead use one or two broader
"best hostels in X" searches per region, populate leaner entries (more `null` fields where the
broader search didn't surface specifics), and explicitly flag lower-confidence inferences (e.g. a
specific chain branch inferred from the chain's known regional presence rather than a directly
verified listing) with a `"LOWER CONFIDENCE ENTRY"` marker in `source_note`.
**Why:** Full deep-dive research per hostel doesn't scale to filling geographic gaps at the volume
needed for realistic matching-engine testing (tens of hostels per region). The tradeoff is made
explicit and auditable rather than pretending every entry has equal confidence — every entry's
`source_note` states plainly which tier it was researched at.
**Follow-up:** initially this distinction only lived in free-text `source_note`, requiring a text
search to find (e.g. `if "lighter-touch" in source_note`) — the same fragile pattern already
identified as a problem elsewhere in this project (see the `near_metro`/`good_for_remote_work`
matching fix). Added a proper structured `research_depth: "deep" | "light"` field to every hostel
instead, backfilled across all 178 entries (68 deep, 110 light) and spot-checked for correctness.
The finer-grained "LOWER CONFIDENCE ENTRY" flag (14 hostels, a subset of "light") remains
text-only for now — a natural candidate for its own structured field later if needed.

### Schema: room-level vs. hostel-level fields
Fields that vary by room type (price, bathroom type, air conditioning, etc.) live in a
`room_types[]` array; fields true for the whole property (staff friendliness, kitchen, location)
live at the hostel level.
**Why:** Real hostels commonly offer both dorms and private rooms with different specs — a flat
schema couldn't represent this accurately. Mirrors how real OTAs structure inventory internally.

### Default-value policy for subjective comfort fields
`pillow_quality`, `mattress_quality`, and `sunlight` default to `"average"` when unverified,
rather than `null`.
**Why:** Silence in reviews about these dimensions is itself a signal — no complaints usually
means "acceptable," not "unknown." Explicitly does NOT apply to factual/structural fields
(occupancy, bathroom type) where `null` genuinely means "we don't know," nor to richer
subjective fields like `cleanliness_signal` or `staff.friendliness`, which stay free-text
because a single-word label would flatten real nuance.

### `accommodation_type` + `has_dorm_beds` + `has_private_rooms` as separate fields
**Why:** The travel list mixed hostels, budget hotels (OYO-style), homestays, and villas — and
backpackers sometimes want a private room even at a hostel. Conflating property branding with
actual room availability would have made filtering wrong for anyone wanting a private room.

### `flagged_issues` — structured "worst case scenario" feature
Each hostel can carry a list of specific, dated, frequency-weighted outlier complaints (e.g. "1
of 2,300 reviews mentioned construction noise, reported ~6 months ago"), separate from the
general `reviews_summary`.
**Why:** Directly answers a real traveler question ("what's the worst that could happen here?")
without either hiding negative reviews or letting a single complaint disproportionately scare
people off. Ties back to the original Medium article's critique of how existing platforms bury
or scatter this kind of information.

### Data sourcing standard
Core global sources: Hostelworld, Booking.com, Tripadvisor, Google Maps, Agoda.
Regional supplements: Goibibo/MakeMyTrip (India), Traveloka (Indonesia), Enuygun.com (Turkey).
Translation is used when a non-English review surfaces something relevant.
**Why:** Relying only on English-language global aggregators biases the dataset toward
international backpacker perspectives and misses domestic-traveler reviews on
regionally-dominant platforms.

### Every hostel entry has a `source_note` field
Documents which platforms were searched, flags uncertainty, and is updated when corrections
are made (e.g. wrong branch of a multi-location chain, traveler's firsthand memory overriding
a search finding).
**Why:** AI-assisted research is a starting hypothesis, not verified fact. Treating it as such —
explicitly, in the data itself — prevents false confidence and makes the dataset auditable.

---

## Tech Debt / Deferred Items

### 🔴 OPEN — Location proximity matching is not distance-aware
`nearby_towns` is a manually-curated list of nearby place names per hostel (e.g. Palolem hostels
list "Patnem", "Colomb", "Agonda"). A match scores a flat +22 points regardless of whether the
place is 2km or 18km away, and the list only recognizes names someone thought to manually add.
**Correct fix (deferred to Phase 4):** Store real lat/long coordinates per hostel (via Google
Places API or similar), geocode search terms on the fly, and calculate real distance
(haversine formula) for both filtering and smooth distance-based scoring.
**Why deferred:** Getting the matching engine functionally correct and connected to the API
was higher priority than precision-tuning proximity search on a 66-hostel MVP dataset.

### 🔴 OPEN — Review data sourcing gaps for Agoda / Traveloka / Google Maps
These platforms are heavily JavaScript-rendered and don't reliably return content through
standard web search/fetch tools — searches often return empty placeholder pages even when a
listing clearly exists.
**Correct fix (deferred to Phase 4):**
- Google Maps reviews: Google Places API (New) — official, legitimate, scalable path
- Agoda / Traveloka: no public reviews API exists at small-developer scale; the real
  industry-standard solution is a paid review-aggregation platform (TrustYou, ReviewPro,
  GuestRevu) that already has licensed pipelines into dozens of OTAs — same approach hotels
  themselves use
- Direct OTA partnerships (Hostelworld Affiliate API, Booking.com Content API) — realistic only
  once there's a working demo to show

### 🟡 OPEN — Several hostels have incomplete price data
Bhakti Kutir, WanderThirst Hostels, Pariwana Hostel Cusco, Casa Kiwi Hostel, Dream Lodge Hostel,
Frendz Resort and Hostel, and Stamps Backpackers Hostel all have `price_range_usd: null` —
pricing wasn't surfaced in available search results.
**Fix:** Needs either a targeted re-search pass or direct booking-site lookup per property.

### 🔵 KNOWN CHARACTERISTIC (not a bug) — Intent parsing isn't perfectly deterministic
Observed directly: the identical query "hostel near Weligama, Sri Lanka" run twice produced
slightly different `vibe_tags` from Claude (`["surf town", "coastal", "beach"]` vs.
`["beach", "surf"]`), which shifted the final match score (39 vs. 43) for the same top result —
not because of any bug in the matching engine, but because the intent-parsing step upstream isn't
guaranteed to tokenize identical input identically every call. The matching engine itself is
fully deterministic given the same parsed intent; the variability lives entirely in the LLM step
before it. Not something to "fix" so much as something to design around — e.g. don't assume
score values are stable/comparable across repeated identical searches, and prefer testing
matching logic directly with a fixed intent dict (as done throughout this log) over testing via
the live API when reproducibility matters.

### 🟡 OPEN — Vibe tag matching is pure text/substring comparison, not semantic understanding
`matching.py` only scores a vibe_tag match when the actual text overlaps (exact match, or one
string is a substring of the other) — it has no concept of related meaning. "calm surroundings"
(query) vs "quiet" (hostel tag) are conceptually near-identical to a human but score zero,
because neither string literally contains the other. Confirmed directly: a query with "calm
surroundings" as a vibe tag scored a hostel tagged "quiet" as a pure location-only match (30
points), with no credit at all for the clearly-related vibe. The semantic understanding only
happens once, upstream, inside Claude's intent-parsing step — everything downstream in
`matching.py` is deterministic string logic with no meaning attached. Proper fix would require
genuine semantic similarity (e.g. embeddings, or a secondary LLM call to judge relatedness)
rather than text matching — a meaningfully bigger feature, not a quick patch. Deferred; not
fixed now, but explicitly tracked so the matching engine's actual capability isn't overstated
later.

### 🟢 RESOLVED — Bangkok had no genuine party hostel, causing valid searches to return zero results
Found via testing "party hostel in Bangkok, want the nightlife": `party_preference: "prefer_party"`
correctly classified, and the scoring math was correct — but `total_matches: 0`. Root cause wasn't
a scoring bug: both existing Bangkok entries (The Victory View, All Day Hostel) have
`party_level: "low"`, and neither was ever meant to be a party hostel. The steep `prefer_party`
penalty (target=6, steepness=15) correctly pushed both to a negative score and filtered them out
— technically correct, but a real content gap, since Bangkok is one of Southeast Asia's best-known
nightlife destinations and the dataset had nothing for it. Fixed by adding two genuine, well-reviewed
party hostels on Khao San Road (Bangkok's classic backpacker party strip): Nomads Bangkok Khao San
Road Hostel and Revolution Khao San by The Bliss, both `party_level: "high"`. Verified directly:
the same query that previously returned 0 results now returns 2, both scoring well. Worth keeping
in mind as a general lesson — a "zero results" outcome is sometimes a genuine data gap rather than
a matching bug, and the fix is adding real content, not tweaking the formula.

### 🟢 RESOLVED — COUNTRY_TO_CONTINENTS lookup fell out of sync after a large data expansion
Found via self-check (not user-reported) after adding 60 new hostels across Europe, Australia, and
South America to close known geographic gaps: the `COUNTRY_TO_CONTINENTS` static lookup in
`matching.py` only covered the ~22 countries present *before* the expansion. 18 newly-added
countries (Argentina, Italy, France, Brazil, Chile, etc.) were completely missing from the table,
which would have silently broken every continent-level search ("hostel in Europe", "hostel in
South America") for most of the new data — the hard location filter would have excluded these
hostels entirely, with no error or warning. Caught by explicitly diffing the dataset's country set
against the lookup table's keys before considering the batch done, rather than assuming the earlier
table would "just still work." Fixed by adding all missing countries; verified directly — a "South
America" search went from 2 total matches (before this batch existed) to 22 after both the data
and the lookup fix.

### 🟡 OPEN — Country-to-continent mapping requires manual sync on every new country added
`COUNTRY_TO_CONTINENTS` in `matching.py` is a hand-maintained dictionary, not derived from any
external source. Already caused one real gap (18 countries missing after the Europe/Australia/
South America batch, caught before commit — see resolved section above). The risk isn't gone,
just currently patched: every future country added to `hostels.json` requires a matching manual
update to this table, with nothing enforcing that the two stay in sync.
**Fix:** Either add a startup check that errors/warns if any country in the loaded hostel dataset
is missing from the lookup table (cheap, catches the problem automatically going forward), or
replace the hand-maintained dict with a proper country→continent library (e.g. `pycountry` +
a continent-mapping package) so it's never manually maintained at all.

### 🟡 OPEN — No virtual environment for the backend
All Python packages (`fastapi`, `uvicorn`, `anthropic`, `python-dotenv`, etc.) were installed
globally on the system Python rather than in a project-specific virtual environment.
`requirements.txt` (generated via `pip freeze`) therefore reflects everything installed
system-wide, not just what VibeMatch actually needs — harmless for now, but could accumulate
unrelated packages over time and make the dependency list noisy.
**Fix:** create a `venv` for the backend (`py -m venv venv`), reinstall dependencies inside it,
and regenerate a clean `requirements.txt` from that isolated environment.

### 🟡 OPEN — Matching score weights are hand-tuned, not validated
Point values (city match = 30, region = 25, vibe tag = 10 each, etc.) were chosen by
engineering judgment during initial build, not derived from any real user behavior or A/B data.
**Fix:** Revisit once there's real usage data on which results people actually click/book.

### 🟡 OPEN — No tiebreaker for equal-scoring hostels
Two hostels with identical scores sort in whatever order they happen to appear in the source
list — not a meaningful order.
**Fix:** Add a secondary sort key (e.g. aggregate review rating, once that field is populated)
so ties resolve meaningfully rather than arbitrarily.

### 🟢 RESOLVED — Location was originally a soft signal, not a hard filter
Found during matching engine testing: a Goa search returned Cambodia/Vietnam hostels near the
top, because location score (up to +30) could be outscored by combined budget+vibe+profile
points (~48). Fixed by hard-filtering by location before scoring runs at all.

### 🟢 RESOLVED — Broad region searches (e.g. "Goa") returned nothing
Original schema only had `city` (e.g. "Palolem") and `country` ("India") — no state/region
level. Fixed by adding a `region` field, backfilled across all 66 hostels.

### 🟢 RESOLVED — Several hostel name/branch mix-ups from research
Multiple properties share near-identical names across different actual locations (Cliff &
Coral's 3 Varkala branches, two separate "Hosteller Fort Kochi" properties, "Sunny Garden
Hostel" vs. actual name "Sunny Hostel Garden", "No Name Hostel" likely renamed to "Nomads
Hostel"). Resolved case-by-case using traveler-provided addresses or Google Maps pins, same
pattern each time — a good reusable workflow for future ambiguous-name cases.

### 🟢 RESOLVED — Partial vibe-tag matching didn't understand negation
Found during real-variety testing after expanding to 116 hostels: a query for "social" party
hostel scored a "not_social" quiet B&B as a top match, because naive substring matching saw
"social" as a text-substring of "not_social" and counted it as a positive match. Fixed by
detecting negation prefixes (`not_`, `non_`, `no_`, `anti_`) and treating a prefix mismatch on
an otherwise-matching core concept as an active penalty ("conflicting vibe") rather than a
false-positive match. Directly validated this was invisible on the smaller 66-hostel dataset
and only surfaced once real vibe-tag diversity (explicitly-quiet properties) existed to expose it.

### 🟢 RESOLVED — traveler_profile vs guest_type singular/plural vocabulary drift
Found via manual inspection of a real search response: the intent parser's prompt was written
with singular traveler_profile examples (e.g. "party_traveler"), while the hostel schema's
`guest_type` controlled vocabulary — built at a different point in the project — uses plural
forms (e.g. "party_travelers"). Exact-match scoring silently failed on every such pair, meaning
a genuinely obvious match scored zero credit. Fixed with a partial-match fallback (same pattern
as vibe_tags) that strips trailing "s" before comparing. Root cause was two schema vocabularies
evolving independently without a shared source of truth — worth designing around if the schema
grows further (e.g. a single shared enum/constants file both the prompt and hostel data draw from).

### 🟢 RESOLVED — Missing price data scored as silently neutral instead of being flagged
When a hostel has no `price_range_usd` on file, it received zero budget-related score either
way — no reward, no penalty — with nothing in the response explaining why. This meant a hostel
with genuinely unknown pricing could rank below a confirmed-affordable one for reasons the
traveler couldn't see, even though the underlying issue was a data gap, not a real mismatch.
Fixed by adding an explicit reason ("price not listed in our data — could not confirm this fits
your budget, check the listing directly") whenever budget was specified but couldn't be checked.
General principle worth carrying forward: anywhere the matching engine can't check something the
traveler explicitly asked about, the response should say so rather than go quiet.

### 🟢 RESOLVED — Continent-level location searches returned zero results
Found via real testing: a search for "Europe" returned nothing, even though the dataset has
several European hostels — location matching only understood city/region/country, with no
concept of continent. Fixed with a lightweight country→continent lookup table used only at
query time (not stored redundantly on every hostel record), including proper handling for
transcontinental countries like Turkey, which now correctly surfaces for both "Europe" and
"Asia" searches.

### 🟢 RESOLVED — Matching engine ignored structured location/remote-work fields
The hostel schema has long included structured boolean fields (`near_metro`, `near_airport`,
`good_for_remote_work`) that were never actually referenced by the scoring logic — a query like
"near a train station" could only match by coincidence via free-text `vibe_tags`, not by
checking the real structured data we already collected. Fixed by adding explicit keyword
detection (transit-related and remote-work-related terms in the parsed vibe_tags) that scores
against these structured fields directly. A good example of the gap between "we collected the
data" and "the product actually uses the data" — worth double-checking for elsewhere in the
schema as the matching engine keeps evolving.

### 🟢 RESOLVED — "Cheap" / qualitative budget language was completely ignored in scoring
Found via testing "cheap hostel in Sri Lanka": the intent parser correctly left `budget_max` as
`null` (since "cheap" has no specific number), but the budget-scoring code only ran `if
budget_max:` — so price played zero role in ranking whenever no exact number was given, even
though the traveler clearly expressed a budget preference. The actual cheapest matching hostel
ranked below a nearly 2x-more-expensive one purely because of an unrelated match. First fix used
fixed dollar thresholds (e.g. ≤$8 → bonus). Superseded by the relative-scoring fix below.

### 🟢 RESOLVED — Fixed-dollar "cheap" thresholds don't work across regions with different price levels
The first fix for the above (fixed thresholds like "≤$8 = cheap") had its own flaw: $20/night is
genuinely cheap for a hostel in Amsterdam but expensive in Bangkok, and no single global dollar
table can reflect that without constant manual re-tuning per region. Replaced with **relative**
scoring: `match_hostels()` computes the actual price spread of whatever candidate pool survived
the location filter (already correctly scoped to city/region/country/continent, whatever grain
was searched) and scores "cheap" relative to that pool's own min/max — the cheapest available
option in *that specific search* scores highest, automatically adapting to local price levels
with no region-specific code. A fixed absolute-dollar table is kept only as a fallback for the
edge case where no price distribution can be computed (e.g. a single priced candidate). Validated
directly: "cheap in Europe" surfaced $8-10 options as top matches, "cheap in Thailand" surfaced a
$3 option as the top match — same code, correctly different absolute numbers per market.

### 🟢 RESOLVED — Compound location strings ("City, Country") broke exact-city matching
Found via testing "hostel near Weligama, Sri Lanka": the intent parser returned the location as
`"Weligama, Sri Lanka"` (compound) rather than isolating just `"Weligama"`. All location matching
used a one-directional substring check (`location in hostel_city`) — which fails when the search
term is *longer* than the field being checked, since a longer string can never be "contained
within" a shorter one. The actual Weligama hostel scored no better than any other Sri Lanka
hostel, despite being the literal city match. Fixed by making city/region/country matching
bidirectional (`location in hostel_city or hostel_city in location`) — the same pattern already
used for `nearby_towns` matching, just never applied consistently to the primary location checks.
General lesson: a fix pattern proven in one part of the matching logic should be audited across
every other place with the same shape of comparison, not assumed to only apply where first found.

### 🟢 RESOLVED — "Budget around $X" was scored identically to "budget under $X"
Found via testing "budget around $10": the traveler correctly pointed out that "around $10" and
"under $10" mean different things — approximate language should tolerate some overage (~20%) and,
more importantly, shouldn't make fine price differences within that zone matter at all ($6 and
$10 should score the same when the ask was "around $10", since the traveler said other criteria
matter more once price is roughly in range). Added a `budget_flexibility` field to the intent
parser ("strict" vs "approximate") and gave the matching engine two different budget-scoring
paths: strict keeps the existing hard-ish ceiling behavior, approximate gives flat equal credit
across a tolerance zone (target × 1.2) so vibe/social/other criteria — not tiny price gaps — drive
the ranking, exactly as the traveler described wanting.

### 🟢 RESOLVED — "Not a party place" didn't actually avoid party hostels
Found via testing "peaceful hostel in Kerala... not a party place": a hostel with
`party_level: "medium_to_high"` and a literal `party_hostel_branding` vibe tag scored the same as
genuinely peaceful hostels, with zero acknowledgment of the conflict. Two compounding bugs: (1)
Claude phrased the anti-party signal as `"non-party"` (hyphen), but the negation detector only
recognized underscored prefixes (`non_`), so it silently failed to recognize the negation at all
— same category of bug as the earlier "surf town" vs "surf_town" issue, now fixed generally by
normalizing hyphens to underscores before checking; (2) more fundamentally, negation handling only
ever compared *text tag against text tag* — it had no mechanism to check the structured
`party_level` field hostels already carry, so a hostel could dodge the check entirely just by not
happening to phrase its party-ness in a way that textually collided with the query. First fix used
a keyword list + binary bucket (avoid-language triggers a flat penalty/reward). Superseded by the
graded fix below.

### 🟢 RESOLVED — Party preference detection didn't handle intensity or a graded party_level scale
Follow-up question worth taking seriously: what should happen for softer phrasing like "not much
a party place" or "priority is calmness" (milder than "not a party place"), against a hostel rated
"low_to_medium" (milder than fully "low")? The keyword-list approach from the first fix couldn't
reliably catch every paraphrase Claude might produce, and even when it did fire, it used a binary
bucket — "low_to_medium" scored identically to "low", and a mild preference was scored identically
to a strong one, with "medium" alone falling into neither bucket at all. Replaced with the same
pattern used for `budget_flexibility`: Claude now classifies intent directly into a structured
`party_preference` field (avoid / prefer_quiet / neutral / prefer_social / prefer_party) with
explicit intensity guidance in the prompt, and matching scores by ORDINAL DISTANCE on a 1-5 party
scale (low=1 ... high=5) rather than a binary bucket. Validated across all 25
preference × party_level combinations before connecting to the real intent parser. General
principle reinforced twice now: prefer a small structured field Claude fills in directly over
inferring nuance from a fixed keyword list, whenever the concept has real gradations worth
capturing.

### 🟢 RESOLVED — "avoid" and "prefer_quiet" incorrectly targeted different ideal party levels
Direct correction from the traveler on the fix above: the first version of ordinal scoring gave
`avoid` a target of `low` (1) but `prefer_quiet` a target of `low_to_medium` (2) — treating a
milder request as if it meant "aim for a slightly livelier result" rather than "still want quiet,
just don't punish moderate levels as harshly." Traveler's framing was correct: "not much a party
place" still means preferring low or near-zero party energy, not low-to-medium. First fix aligned
both to target=1 (`low`) with different steepness. Refined further below.

### 🟢 RESOLVED — "low" party_level was treated as a perfect match for "avoid", when it shouldn't be
Second round of the same correction: the traveler pointed out that even "low" still has *some*
party element, and a strong "avoid" request shouldn't treat it as a perfect match — a hostel with
"low_to_medium" or higher shouldn't realistically show up at all for someone who explicitly wants
to avoid parties. Fixed by shifting the target for `avoid`/`prefer_quiet` from 1 (`low`) to a
*virtual* 0 — one step below the lowest value our schema actually tracks — so `low` is always
scored as "closest available, not perfect" rather than a maximum. Combined with steepness: `avoid`
now scores `low` at only +5 and `low_to_medium` at -10 (likely dropping it from results entirely,
since the matching engine filters out any non-positive total score), while `prefer_quiet` scores
`low` at +13 vs `low_to_medium` at +6 — both still positive but clearly differentiated, matching
the traveler's exact description: "no party gets higher score, low gets some score too, low to
medium gets less than low." The same logic was mirrored symmetrically on the opposite end
(`prefer_social`/`prefer_party` target shifted from 5 to a virtual 6, one step above `high`) so a
`high`-party hostel isn't treated as an unbeatable ceiling either — confirmed as the desired
behavior rather than reverted. Validated numerically against the traveler's own description before
being accepted, not just visually inspected.

### 🟢 RESOLVED — Score was an opaque total with no per-factor breakdown, and result counts weren't reported
Two product asks handled together since they touched the same code: (1) the API response had no
way to tell how many hostels actually matched a query before truncating to the top 10 — a search
returning "10 results" looked identical whether 10 or 400 hostels actually qualified; (2) the
`reasons` field was plain text strings with no attached point values, so there was no way to see
exactly how a final score was assembled without manually re-deriving it. Fixed by rewriting
`score_hostel()` around a single `add(points, reason)` helper that records every contribution as
a `{"points": int, "reason": str}` entry in a `breakdown` list, with the final score computed as
their sum (rather than tracked separately and potentially drifting out of sync) — and by having
`match_hostels()` return both `total_matches` (full candidate count before truncation) and the
truncated `results` list, both surfaced in the `/search` API response.

### 🟢 RESOLVED — Assuming Claude's response content[0] is always the text block crashed on some queries
Found while testing whether `party_preference` generalizes correctly beyond party-related
"avoid" language (e.g. "avoid traffic and crowded areas"): the query triggered a 500 error,
`AttributeError: 'ThinkingBlock' object has no attribute 'text'`. Root cause: `parse_intent()`
assumed `message.content[0]` is always the text response, but Claude's API can return multiple
content blocks — including a `ThinkingBlock` (internal reasoning) ordered BEFORE the actual
`TextBlock`, which appears to happen more often on queries with more nuanced or mixed signals
(exactly the kind of query being used to stress-test the party_preference scoping). Fixed by
looping through all content blocks and selecting whichever one has `type == "text"`, instead of
assuming position — with a clear error listing the actual block types received if none is found,
rather than a cryptic AttributeError. Unrelated to the party_preference logic itself, but only
surfaced because more adversarial/edge-case queries were being tested deliberately before
committing — a good argument for that habit continuing.

---

## Chain / Brand Patterns Noticed in the Data

Worth tracking as its own note — several multi-property hostel brands showed up repeatedly
across the dataset, which could eventually become a matching signal itself ("if you liked X,
try their sister property in Y"):

- **Mad Monkey** — Phnom Penh, El Nido (Philippines)
- **Zostel** — Pushkar, Kathmandu
- **Vietnam Backpacker Hostels (VBH)** — Hanoi, Saigon, Hoi An
- **Central House** — Istanbul Taksim, Marrakech Medina
- **M Box** — Seminyak (Bali), Gili Trawangan
- **Onederz** — Phnom Penh, Siem Reap (5+ properties across Cambodia per one review)
- **The Hosteller** — multiple India locations (source of one of the branch-confusion issues above)
