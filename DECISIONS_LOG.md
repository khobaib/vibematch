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

### 🟢 RESOLVED — Vibe tag matching was pure text/substring comparison, not semantic understanding
`matching.py` only scored a vibe_tag match when the actual text overlapped (exact match, or one
string a substring of the other) — it had no concept of related meaning. "calm surroundings"
(query) vs "quiet" (hostel tag) are conceptually near-identical to a human but scored zero,
because neither string literally contained the other. Confirmed directly: a query with "calm
surroundings" as a vibe tag scored a hostel tagged "quiet" as a pure location-only match (30
points), with no credit at all for the clearly-related vibe. Fixed by adding a genuine semantic
layer: Claude (Haiku 4.5) writes a natural-language `vibe_profile` paragraph per hostel from its
existing structured fields (228 hostels, ~$0.35 total), each profile is embedded via Voyage AI
(`voyage-4`), and at search time the traveler's raw query is embedded the same way and compared
via cosine similarity — added to `matching.py` as a new, auditable breakdown line
(`compute_semantic_entries()`), scored relative to the current candidate pool (same pattern as
the relative-cheapness budget fix below). Validated directly: querying "a quiet peaceful place
great for remote work, not a party scene" surfaced hostels whose profiles explicitly said
"quiet," "peaceful," or "low-key" at the top, entirely via vector similarity — no tag overlap
required. Separately validated that a known party hostel's nearest neighbors were all other
party hostels, with a meaningfully lower cross-similarity to the calm cluster (0.66) than either
cluster's internal similarity (~0.80+) — confirming the embedding space genuinely separates
"vibe" as a concept. See the new open item below for what's *not* yet validated about this.

### 🟡 OPEN — Semantic similarity and structured signals can disagree, not yet validated across many real cases
The new semantic layer (see resolved item above) and the existing structured scoring
(`party_preference`, exact/partial `vibe_tags` matching) are deliberately independent sources of
evidence — each reasons about the query in its own way and can legitimately reach different
conclusions about the same hostel. Observed directly in a real live search ("a chill hostel in
Goa good for remote work, not too partyish"): several results received both a `-1` penalty for
"party vibe (medium) doesn't closely match your stated preference" *and* a positive semantic
bonus (e.g. +9, +8) for matching "chill/remote work" — each signal being independently honest
about what it measures, not a bug, but also not yet stress-tested against the kind of adversarial
cases already logged elsewhere in this file (the "calm vs quiet" case above, the Weligama
non-determinism case, etc.). Specifically not yet known: how often the two systems disagree, in
which direction, and whether the current point weighting (semantic capped at 15, comparable to a
single vibe-tag category) is actually well-calibrated or just a reasonable-sounding starting
guess.
**Fix:** Task #6 (validate semantic matching against known tech-debt cases) — run the semantic
layer against a broad set of real queries, including the existing documented adversarial cases in
this log, and specifically log cases where semantic and structured scoring disagree so the
pattern (if any) becomes visible rather than anecdotal.

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

### 🟢 RESOLVED — flagged_issues had no severity signal, only frequency — AI explanation risked softening serious issues
Found via testing the new "why we matched this" AI explanation feature with "safe hostel in
Pushkar": Madpackers Pushkar's genuine safety incident (a report of someone entering a female
traveler's dorm at night) was correctly surfaced, but the explanation's closing tone — "just
something to keep in mind if extra vigilance matters to you" — read more like a minor
preference caveat than an appropriately weighted safety concern. Root cause: `flagged_issues`
only ever tracked `frequency` (how often something happens), with no signal for `severity` (how
much it matters if it does) — the AI had to infer severity purely from reading raw issue text,
with nothing stopping "isolated" framing from softening even a serious concern. Same lesson as
`budget_flexibility`/`party_preference`/`near_metro`: inferring nuance from unstructured text is
fragile, an explicit structured field is reliable. Fixed by adding `severity: "minor" |
"moderate" | "serious"` to all 4 existing flagged_issues entries (backfilled by hand given the
small count) and updating the explanation prompt with an explicit rule: severity must drive tone
regardless of frequency — a "serious" issue gets real weight even if it's a single isolated
report, while a "minor" issue can be softened by its rarity. Frequency and severity are
explicitly separated as two different axes the model must reason about independently.

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

### 🟢 RESOLVED — AI explanation as one dense paragraph didn't fit the actual use case
Raised directly by the traveler: backpackers often check search results while walking, standing,
or otherwise not in a position to read a full paragraph — a wall of prose is the wrong format for
that moment. Redesigned the `/explain` response from free text into structured JSON: a short
`verdict` headline (under 10 words), a variable-length `highlights` list (1-4 short fragments, not
full sentences), and a variable-length `heads_ups` list (0+ fragments, only present when genuinely
relevant). Explicitly designed to NOT force every explanation into a rigid fixed shape — highlight
count and heads_up count both flex based on what's actually true for that hostel, rather than
being padded or truncated to hit an expected number. Frontend renders this as a scannable
checkmark/warning-icon list instead of a paragraph. The existing raw score-breakdown button was
kept as-is for anyone who wants the fuller technical detail — this format is specifically the
fast-glance layer, not a replacement for depth.

### 🟢 RESOLVED — heads_ups instruction said "the most relevant one" but real behavior (and validated as correct) surfaces multiple
During testing of the redesigned format above, "safe hostel in Pushkar" surfaced BOTH of
Madpackers Pushkar's flagged issues (the serious safety report AND the moderate cleanliness
report), even though the original prompt instruction said to include only "the most relevant
one" (singular). Confirmed this was actually the better behavior, not a bug — for a
safety-focused query, showing every genuinely relevant issue (not just the top one) gives more
complete due diligence, and the two issues were already correctly ordered most-severe-first.
Updated the prompt instruction to explicitly match this: "include EVERY flagged issue that's
genuinely relevant... not just one," with an explicit ordering rule (most severe first), so this
becomes documented intended behavior rather than a lucky one-off result.

### 🟢 RESOLVED — Vite's default index.css text-align: center leaked into the styled UI
Found via screenshot review after the structured AI-note redesign: hostel names, locations, and
buttons were unexpectedly center-aligned instead of left-aligned as designed. Root cause: Vite's
default project scaffold ships `#root { text-align: center; }` in `index.css`, which had never
been cleaned up and was silently overriding the new design system once real content made the
misalignment visible enough to notice. Fixed defensively — rather than hunting through and
editing `index.css` (risk of missing something else hiding there), added an explicit
`text-align: left` directly on `.vm-app`, which wins regardless of whatever `index.css` contains
because it's more specific to the actual component tree.

### 🟢 RESOLVED — "safety_concern_flagged" vibe tag ironically boosted score for "safe hostel" searches
Found via screenshot review: Madpackers Pushkar's own `vibe_tags` included `"safety_concern_flagged"`
— a tag added specifically to signal its dorm-entry safety incident. A "safe hostel in Pushkar"
search then matched `"safety"` as a substring of `"safety_concern_flagged"` and awarded +4
positive points, treating the tag that exists to WARN about a safety problem as evidence of
safety — backwards. Same root cause as the earlier `not_social` negation bug (naive substring
matching, no semantic understanding), but a new variant: not a negation prefix, but a word
embedded in a compound tag carrying the opposite real-world meaning from the isolated word.
Rather than attempting to generically teach the matching code to detect this class of irony
(fragile), fixed at the data level by renaming the tag to `"guest_incident_reported"`, which
shares no misleading substring with common positive search terms. Verified directly: the same
search no longer produces the false-positive match. Worth remembering as a naming discipline
going forward — avoid tag names containing words that could read as positive in isolation when
the tag's actual meaning is a warning.

### 🟢 RESOLVED — No hostel had a genuine positive safety signal after removing the false one
Direct follow-up to the fix above: after removing the false `safety_concern_flagged` match, a
check confirmed ZERO hostels in the entire 178-hostel dataset had any tag containing "safe" or
"safety" — meaning a genuine "safe hostel" search had nothing real left to match against at all,
only location and coincidental unrelated overlaps. This was a real gap distinct from the bug just
fixed: removing a wrong signal isn't the same as having a correct one. Searched existing
structured data (`guest_type` containing `female_solo_friendly`, `exclusive_features` mentioning
CCTV/locks/secure storage) for hostels with already-documented, genuine safety-relevant evidence,
and added an honest positive vibe tag to 10 hostels based specifically on what each one's own data
already supported — e.g. `female_solo_safe` for hostels with documented female-solo-friendly
status, `cctv_secure` for a hostel with actual CCTV mentioned, `secure_storage` for one with
documented lockable storage. Deliberately did NOT add a tag to Madpackers Pushkar despite it also
surfacing in this search — it has a genuine documented safety incident, so a positive safety tag
there would be actively misleading. Tag names were chosen to contain "safe"/"secur" specifically
so they work with the existing substring-matching logic without requiring any code changes — a
pure data enrichment, verified directly against a live "safe" search.

### 🟢 RESOLVED — Initial safety-signal search was too narrow; a full sweep found 3 more real cases
Directly prompted by the traveler asking whether guest review text (not just structured fields
like `guest_type`) could also reveal safety signal. The first pass only searched a narrow phrase
set (`"solo female"`, `"female traveler"`) across a couple of fields. A broader keyword sweep
(`safe`, `secure`, `sketchy`, `unsafe`, `gated`, etc. across `reviews_summary`,
`cleanliness_signal`, `staff.friendliness`, `location.notes`) surfaced 5 hits, one of which
(Tendean Residence, "gated") turned out to be a false positive from the search itself — matching
inside the word "agg**regated**", the same substring-matching trap this whole investigation was
about, now caught in the checking process itself. Of the 4 genuine hits: added positive tags to
2 hostels with real evidence (`safe_residential_area` for All Day Hostel @ BTS Bang Chak,
"quiet and safe residential-feeling area"; `guests_feel_safe` for Onederz Phnom Penh, "guests
report feeling safe" despite the area being "somewhat seedy at night"); converted a genuine
negative finding for Lotus Garden Hostel ("area can feel a bit sketchy at night") from a vibe_tag
that already existed but was invisible to the AI explanation feature into a proper structured
`flagged_issue` with severity/frequency, so it can actually be surfaced and reasoned about by that
feature going forward. General lesson: an initial "comprehensive" search is often narrower than it
feels at the time — worth periodically widening the net rather than assuming the first sweep
caught everything, and worth being just as skeptical of one's own verification searches as of the
original bug.

### 🟢 RESOLVED — "avoid"/"prefer_quiet" party scoring treated a real ambiguity (party_level "low" meaning both "genuinely silent" and "a little activity") as a single value, and rewarded it instead of matching intent strictness
Surfaced via direct product review of Task #6 validation results, not automated testing. Two
compounding problems, found together: (1) `party_level: "low"` was being used across the dataset
to mean two genuinely different things — a hostel with truly no social/party element, and one with
occasional light activity (weekend gatherings, a chatty common room) — with nothing distinguishing
them. (2) The scoring formula (`bonus = 20 - distance*steepness` against a virtual target below the
scale's floor, since no true "zero" category existed) meant even the strict `"avoid"` preference
*rewarded* a "low" hostel (+5), on the theory that it was "the closest available option." Direct
critique from real travel experience: someone who explicitly says "avoid party" wants a genuinely
quiet hostel to score well and a "some activity" hostel to score poorly — rewarding the ambiguous
middle ground undersells how much that stated preference should matter. **Fixed with three
changes:** (a) added a real `"none"` tier to `party_level` — `reclassify_party_level.py` used
Claude to re-read each of the 49 hostels tagged `"low"`'s *existing* data (`reviews_summary`,
`social_vibe`, `flagged_issues`, `vibe_profile` — no new web research needed) and reclassify: 13
had clear, explicit evidence of genuinely zero social element ("no-party policy," "not_a_party_
hostel," enforced silent hours) and moved to `"none"`; 36 had real light-social evidence (rooftop
gatherings, shared meals, communal activities) and correctly stayed `"low"`; 0 were low-confidence,
meaning the existing data already had clear signal either way for every case. (b) Replaced the
single distance-based formula with an explicit, hand-tuned point table per `party_preference`
category (values set through direct product discussion, not derived from a formula, since the
desired curve shapes for "avoid" vs. "prefer_quiet" are asymmetric and a shared formula can't
express that):

| party_level → | none | low | low_to_medium | medium | medium_to_high | high |
|---|---|---|---|---|---|---|
| avoid (strict) | +20 | -10 | -20 | -30 | -40 | -50 |
| prefer_quiet (soft) | +10 | 0 | -5 | -10 | -15 | -20 |
| prefer_social (soft, mirrored) | -20 | -15 | -10 | -5 | 0 | +10 |
| prefer_party (strict, mirrored) | -50 | -40 | -30 | -20 | -10 | +20 |

(c) This level of negative scoring is only safe because of the next entry below — without it,
"avoid" + "high" scoring -50 could have produced empty result sets for genuinely valid searches.
Verified directly: an "avoid party" query now surfaces the newly-reclassified `"none"` hostels as
perfect +20 matches at the top of results, exactly as intended.

### 🟢 RESOLVED — Hostels scoring ≤ 0 were dropped from results entirely instead of just ranked low
Found via the same Task #6 review, testing "party hostel in Bangkok, want the nightlife": the 3
Bangkok hostels that aren't party-oriented scored strongly negative (`prefer_party` penalty against
their `low`/`none` party_level) and were silently removed from the response, not merely ranked
last. Direct critique: this is why party-preference scoring had to stay artificially gentle for so
long — punishing a mismatch harder always risked pushing every candidate below zero and reproducing
the exact "Bangkok returns 0 results" failure already fixed once (see the Bangkok RESOLVED entry
above) for a different underlying reason. Showing nothing is worse than honestly showing "here's
the closest we've got, though nothing here is a great fit" — gating on score sign conflates
*ranking* (a relative judgment, which scoring is good at) with *gating* (an absolute judgment about
whether something is worth showing at all, which a hostel with real location/vibe overlap almost
always is, even if one criterion scores badly). **Fixed:** `match_hostels()` no longer drops a
hostel for scoring ≤ 0 — a hostel is excluded only if it has zero breakdown entries at all (nothing
about the search criteria applied to it whatsoever, e.g. an unconstrained query against a hostel
with no location or vibe overlap to evaluate). Everything genuinely evaluated is shown, ranked;
`total_matches` keeps its original meaning (count of score > 0 "genuine" matches, preserving
existing callers'/tests' expectations), while a new `is_recommended: bool` field on each result
(true iff score > 0) lets the frontend/AI-explanation layer distinguish "a real match" from "the
least-bad option available" rather than presenting both with equal confidence. This change is what
makes the strict party-preference table above safe to ship — a badly-scoring hostel now ranks near
the bottom instead of vanishing.

### 🟡 OPEN — A nuanced dual-mode query ("focus during the day, meet people at dinner") got ranked purely by party_level, ignoring the work/focus half entirely
Found via Task #6 validation. Query: "somewhere I can focus during the day but still meet people
over dinner." Claude's intent parser collapsed this into a single `party_preference: "prefer_
social"` value — the schema has no way to represent "quiet mornings, social evenings" as two
separate signals — and every one of the top-ranked results won purely on `party_level` closeness to
that single target (up to 20 points), with **zero** breakdown entries referencing remote work,
coworking, or focus at all. Confirmed this isn't just under-weighting: re-running with a reworded
query ("...focus **in work** during the day...") produced an almost identical parsed intent and,
critically, the same structural gap — the work/focus dimension of the query is not represented
anywhere in final ranking, regardless of phrasing. Root cause is two-fold: (1) `party_preference`
as a single categorical field cannot express time-varying preferences within one stay, and (2) even
where `vibe_tags`/semantic similarity *did* capture the work-focus nuance, `party_preference`'s
point budget (up to 20) dominated the additive total enough that those signals never surfaced the
right hostels into the top ranks for this query. **Not fixed yet** — this needs either a richer
intent schema (e.g. splitting "daytime vibe" from "evening vibe" as separate preferences) or a
rebalancing pass across all scoring categories' point budgets, both real design work rather than a
quick patch.

### 🟢 RESOLVED — `views` field (`has_view`, `view_type`, `view_from`) was collected but never used in scoring, and the underlying data wasn't clean enough to match against reliably
Found via direct product review while testing "I want to hear some sound of waves in a calm
surroundings" — confirmed via code search that `matching.py` never referenced the `views` field
anywhere. A hostel could be genuinely oceanfront with real wave/view data on file, but a query about
that experience could only score via incidental `vibe_tags` overlap or the semantic layer — the
structured, already-collected view data contributed nothing. Same category of gap as the
already-resolved "matching engine ignored `near_metro`/`good_for_remote_work`" issue above. **A
second, deeper problem surfaced while investigating the first:** `view_type`/`view_from` were
originally free-text with no controlled vocabulary — inconsistent formatting (`"rooftop terrace"`
vs `"rooftop_terrace"`), multi-concept strings joined together (`"balcony views, cliff-adjacent"`),
and values mixing `view_from`-style info into `view_type` (`"city view balcony in some rooms"`).
Wiring the field into scoring without fixing this first would have produced unreliable matches.
**Fixed with two changes, done together:** (a) `normalize_views.py` re-read each of the 62
`has_view: true` hostels' *existing* free-text values (plus `vibe_profile`/`reviews_summary` for
context — no new web research) and normalized both fields into fixed controlled vocabularies, as
lists rather than single strings (so a hostel with two view types, e.g. `"garden and temple
views"`, correctly becomes `["garden", "temple"]` instead of one lossy string). The initial
vocabulary (16 view types, 10 view-from locations) was expanded by 3 after the first real run
surfaced genuine gaps — `park`, `volcano`, and `courtyard` — categories the model correctly refused
to force into a lossy "other" bucket. Original free-text values are preserved in a new
`original_free_text` field for auditability. (b) `matching.py` step 9 now checks
`views.has_view`/`views.view_type` directly: a query naming a specific view type (e.g. "mountain
view") that matches a hostel's actual `view_type` list earns +12 per matched type; a generic
"scenic view" style query against any hostel with a real view earns a smaller +6, naming the actual
view(s) in the reason so it stays auditable. Verified directly: "hostel with a mountain view"
correctly surfaced hostels with `mountain` in their normalized `view_type` list with a +12
breakdown entry; the original "sound of waves" query correctly surfaced 9 real oceanfront hostels
across the full (unfiltered) 228-hostel pool with a `+12 has an ocean view` entry — they didn't
crack the top 5 in that particular unconstrained search only because other signals (calm/peaceful
tag matches, party-level scoring) outweighed the view bonus for that specific query, not because
the fix failed.

### 🟡 OPEN — Schema is missing several fields real travelers consistently care about
Prompted directly by the traveler's own travel experience, cross-checked against hostel-booking
guidance research (hostelz.com, hostelgeeks.com) to confirm these are genuinely common decision
factors, not just personal preference. Full candidate list surfaced:

- **Bed bug / pest report signal** — currently only expressible buried inside free-text
  `flagged_issues` (one real case already exists: Habitat Hostel Koh Chang's 2017 report), with no
  way to filter or score on it directly. One of the most consistently-cited traveler concerns across
  every source checked — dedicated pest-reporting guides exist across major travel sites.
- **Lockers / security specifics** — no structured field for in-dorm lockers, 24-hour reception, or
  keycard/access-control, despite these ranking among the top-cited decision factors in every source
  reviewed. `services.deposit_required` and `cleanliness_signal` exist but don't cover this.
- **Hair dryer availability** — not represented anywhere in the current schema.
- **Clothes-drying facility** — distinct from `services.laundry_service` (already exists): "can I
  wash clothes" and "can I actually dry them" are different practical questions, especially in humid
  climates.
- **Boutique vibe** — RESOLVED, see the entry below. Was reclassifiable from existing data (no new
  research needed), so it was pulled out of this list and done immediately rather than held for the
  larger research pass.
- **Swimming pool** — NOT actually missing; `facilities.swimming_pool` already exists in the schema.
  Under-utilized in matching, not a data gap.
- **Curfew policy** — a real dealbreaker for some travelers (some hostels lock doors overnight), not
  currently tracked. Folded into the upcoming larger research pass (same cheap-lookup tier as hair
  dryer — a factual yes/no most hostel listings state directly).
- **Room-noise placement** ("room facing a noisy street vs. a quiet courtyard") — explicitly a
  ROOM-level attribute, not a hostel-level one (per direct correction) — belongs inside each
  `room_types[]` entry (near the existing `air_flow`/`sunlight` room-level fields), not as a
  hostel-wide field, since it can vary dramatically between rooms in the same building. Kept
  deliberately separate from the other fields above/below since it's a different schema shape
  problem (room-level, not hostel-level), not just a different research cost.

**Decision: scoped down to a focused first pass** rather than tackling all of these at once, since
adding a schema field is trivial but backfilling real, sourced data across all 228 hostels is a
genuine research cost each time (comparable to the `vibe_profile` generation or party-level
reclassification efforts above). First batch selected for clearest traveler impact: (1) bed bug/pest
signal, (2) lockers/security, (3) hair dryer + drying facility, (4) curfew policy (folded in later,
same cheap-lookup tier) — combined into one research pass since all four are quick factual lookups
rather than deep research. Room-noise placement stays deferred separately (different schema shape).

### 🟢 RESOLVED — Nearby attractions field added, and boutique-style added; both normalized from
### existing data (no new research)
Two more gaps, both fixable without new web research:

1. **Nearby attractions**: raised directly by the traveler — "when as a traveler we go to a hostel,
   we always look for nearby attractions, cafes, fun/chill places, nature... within 3-5 kms, which
   is walkable." `location.nearby` already existed for 118/228 hostels, but only as informal
   free-text strings ("Palolem Beach (13 min walk)", "Odayam Beach (80m)") with distance/time
   embedded inconsistently, no type classification, and it was never referenced anywhere in
   `matching.py` — pure dead data.
2. **Boutique vibe**: previously only expressible as an unstructured `vibe_tags` string, with no
   reliable way to filter or score on it. Confirmed via `accommodation_type` distribution
   (215 hostel / 6 guesthouse / 4 hotel / 2 homestay / 1 villa) that "boutique" isn't currently
   modeled as any kind of category — it's a style descriptor that cuts across accommodation types
   (a boutique hostel is still fundamentally a hostel), so it became a new `is_boutique_style`
   boolean rather than a new `accommodation_type` value.

Both fixed together via `normalize_nearby_and_boutique.py` — same "re-read existing data only,
default conservatively, no fabrication" methodology already used for `party_level` and `views`:
`location.nearby` restructured into `[{"name", "type", "distance_km", "walkable"}]` (type is one of
`cafe|nature|landmark|nightlife|beach|viewpoint|market|other`; `distance_km` is null rather than
guessed when the source text gives no real distance/time signal — e.g. "gateway to Yala National
Park" correctly produced `distance_km: null`, not a fabricated number), with the original free-text
preserved in `location.nearby_raw_text`. `is_boutique_style` classified for all 228 hostels,
defaulting to `false` unless there's clear signal (25 came back `true`) since boutique is the
exception, not the default.

Verified: 0 vocabulary violations, 0 structural violations across all 118 restructured entries;
spot-checked output reads correctly (e.g. Bedrock Boutique Hostel — tagged `luxury_hostel` /
`amphitheatre` / `club_themed_common_areas` — correctly classified `is_boutique_style: true`).

Both wired into `matching.py` as new auditable scoring steps: nearby attractions match a query's
named category (e.g. "beach", "nightlife", "cafe") against the hostel's actual `nearby` list, deduped
to the best entry per type, with `+10` if walkable and `+6` if not (e.g. "walkable to Arugam Bay
beach (beach), matching what you're looking for nearby"); boutique-style query language ("boutique",
"design hostel", "upscale", etc.) earns `+10` against hostels with `is_boutique_style: true`. Both
verified live against real queries.

**Still open**: the other 110 hostels have NO `location.nearby` data at all — that requires genuine
new research (not just re-reading existing data) and is scoped into the larger data-enrichment pass
below, alongside bed bugs/lockers/hair dryer/curfew.

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
