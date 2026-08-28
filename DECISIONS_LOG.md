# VibeMatch — Decisions & Tech Debt Log

*A running record of product/technical decisions and known shortcuts, kept during early-stage
development ahead of a formal PRD. Organized so it can be merged into a PRD later — each entry
has the decision, the reasoning, and the date/context it was made in.*

---

## How to Use This Doc

- **Decisions** = choices we made deliberately, with reasoning, that we're standing behind for now
- **Tech Debt** = known shortcuts or limitations we accepted on purpose, with a plan to revisit
- **Field/Feature Backlog** (below) = new schema field ideas that come up mid-conversation, parked
  here instead of built immediately, since each new field means a real research/enrichment cost
  across the whole dataset (comparable to the bed-bugs/lockers/curfew pass above) — not something
  to take on reflexively every time an idea comes up. Reviewed and triaged periodically (~biweekly)
  rather than per-idea.
- Nothing here is final — this is a log of *current* thinking, not commitments carved in stone

---

## Field/Feature Backlog

*New data fields worth adding eventually, captured here as they come up rather than built
immediately. Each one needs the same two-part cost estimate before starting: (1) is this
re-classifiable from data we already have (cheap, `normalize`-style), or does it need genuine new
research per hostel (real cost, `merge`-style)? (2) is it worth wiring into `matching.py` scoring,
or just useful as display/explanation context? Triage these together during the periodic review
rather than one at a time.*

**Status key for entries below**: 🔵 *schema + scoring logic built, mechanically validated against
a synthetic fixture, waiting only on real research* vs 🟣 *idea only, nothing built yet*.

- 🔵 **DIY breakfast available** (`kitchen_food.diy_breakfast_available`, bool) — distinct from
  `free_breakfast` (a full served meal) and `kitchen_available` (a usable kitchen exists). This is
  the middle case: bread/jam/butter/tea left out for guests to assemble their own simple breakfast.
  Schema + scoring built 2026-08-28 (step 19, food self-sufficiency combo), validated against
  `test_fixtures/synthetic_test_data.json` (backlog_fields section, run via `python validate.py
  backlog_fields`). Needs genuine new research — not reclassifiable from existing fields.
- 🔵 **Kitchen utensils quality** (`kitchen_food.kitchen_utensils_quality`, none/basic/good) —
  `kitchen_amenities` already exists as a list but doesn't capture usability. Schema + scoring
  built 2026-08-28 (step 19). Possibly reclassifiable from existing `kitchen_amenities` list
  contents rather than needing new research — worth checking at triage before assuming a full
  research pass is required.
- ✅ **`free_breakfast` wiring** — turned out to already be REAL data (37 true / 19 false / 226
  total), not a backlog item at all. Wired for real 2026-08-28 (step 19) — no fixture, no research
  needed, done.
- 🔵 **Wifi quality** (`facilities.wifi_quality`, none/weak/good/excellent) — only 11/226 hostels
  mention "wifi" anywhere in free text right now; `good_for_remote_work` is the only real proxy.
  Schema + scoring built 2026-08-28 (step 17, daytime work-focus combo), validated against the
  synthetic fixture. Needs genuine new research.
- 🔵 **Desk/seating setup for laptop work** (`facilities.desk_setup`, none/basic/good) — same
  context as wifi quality. Schema + scoring built 2026-08-28 (step 17). Not reclassifiable from
  existing data; needs new research.
- 🟣 **Common-area AC** — `facilities.lounge_has_ac` already exists as a field (already wired into
  step 17) but is populated for only 4/226 hostels. Likely reclassifiable from existing
  review/facility text for many hostels — worth checking at triage before assuming full new
  research is needed.
- 🔵 **Communal dinner / family-style meal flag** (`social_vibe.communal_dinner_available`, bool) —
  distinct from `social_activities` (organized events) — specifically about shared meal culture.
  Only 12/226 hostels mention "dinner" anywhere in free text currently. Schema + scoring built
  2026-08-28 (step 18, evening social-mixing combo), validated against the synthetic fixture.
  Needs genuine new research.
- 🔵 **WhatsApp/community group available** (`social_vibe.whatsapp_community_group_available`,
  bool) — raised 2026-08-28: a real, strong, and DISTINCT social signal from generic organized
  activities — it's the actual mechanism guests use to coordinate hangouts/day-plans, and part of
  why travelers return to the same hostel on a later trip (they're still in the group). Schema +
  scoring built the same day (step 18, weighted above generic activities/dinners at +8), validated
  against the synthetic fixture. Needs genuine new research — likely a targeted review-text search
  ("WhatsApp group", "add you to the group", etc.), same search pattern as the earlier
  bed-bugs/lockers pass.
- 🔵 **`daytime_party_level` / `evening_party_level`** (same vocab as the existing `party_level`) —
  schema + scoring logic built 2026-08-27/28 (see the Fix B TECH DEBT entry above), mechanically
  validated against `test_fixtures/synthetic_test_data.json` (daynight section, run via `python
  validate.py daynight`). Needs genuine new research, likely starting with hostels most plausibly
  having real day/night contrast.
- 🔵 **Solo-vs-group traveler ratio** (`social_vibe.solo_group_ratio`,
  mostly_solo/mixed/mostly_groups) — `guest_type` only supports free-text-derived tags (188/226
  mention "solo" somewhere, only 1 mentions "group") with no real ratio signal. Schema + scoring
  built 2026-08-28 (step 18, takes priority over the older `guest_type` heuristic when present).
  Needs genuine new research.

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

### 🟢 RESOLVED — Task #6: semantic matching validated live against known tech-debt cases
Ran `validate.py semantic` (all 8 cases, live Claude + live Voyage, from the user's own machine —
this sandbox cannot reach `api.voyageai.com`, see the correction entry above) against 226 real
hostels / 228 embeddings. Results:
- **"Calm surroundings" case (the original bug that opened this item): confirmed fixed.**
  Claude's parser now extracts `calm/relaxing/peaceful`, which directly matches the hostel's real
  `peaceful` tag for some results — but Kamasanti Hostel ranked #2 with *no tag-match line at
  all*, credited purely by a `+15 vibe profile semantically matches` line. That's the semantic
  layer doing genuinely independent work, not just riding on better tag extraction.
- **Weligama non-determinism case: stable.** Same query, consistent location scoring, semantic
  similarity held in a tight 0.58–0.64 band across the top 5 — no wild swings.
- **Bangkok party regression check: clean, no disagreement flags.** Real party hostels ranked
  top, quiet hostels correctly penalized (-40/-50), ordering unchanged from the pre-semantic fix.
- **"Absolutely not a party hostel" (strong avoid signal): clean.** All top 5 genuinely
  no-party hostels; semantic layer never overrode or diluted the explicit rejection.
- **Bed bugs/lockers and curfew/hair-dryer/drying (new services-field validation): both clean.**
  No bed-bug-flagged or real-curfew hostel leaked into top 5; comfort-keyword bed-bug bonus,
  locker/hair-dryer/drying bonuses all fired independently without interfering with each other.
- **Goa remote-work case ("chill... good for remote work, not too partyish"): disagreement
  pattern reproduces, exactly as originally logged.** Dreamcatcher House & Hostel, Hashtag Rooms,
  and BunkNBrew all got both a real structured penalty (party vibe medium/low_to_medium doesn't
  match `prefer_quiet`, -5 to -10) *and* a positive semantic bonus (+8 to +15) for the hostel's
  vibe-profile text still reading as "chill/remote-work-friendly." Each score is individually
  correct given what it measures — this isn't a bug.

**Decision:** keep the two signals fully independent (no dampening). Both scores are honest about
what they measure — the structured penalty says "this hostel's overall party intensity doesn't
match what you asked for," the semantic bonus says "this hostel's description is topically very
similar to your query" — and the net score already reflects that tradeoff without needing a new
suppression rule. Task #6 is CLOSED on this basis; dampening semantic-vs-structured disagreement
is not planned work, just something to keep an eye on if it starts producing genuinely bad
top-line rankings in practice.

### 🟢 RESOLVED — Remaining 4 test queries (daynight + backlog_fields suites) validated live, plus a wording bug found and fixed
Completes all 12 test queries across the three `validate.py` suites (8 semantic + 1 daynight + 3
backlog_fields). `daynight` (Fix B split-scoring mechanism) and `backlog_fields` (7 backlogged
fields' scoring logic) both ran live against their synthetic fixtures — real rankings shifted
correctly once fake day/evening party levels, wifi/desk, WhatsApp/communal-dinner, and DIY
breakfast/kitchen-utensils values were overlaid, and both runs' sanity checks confirmed
`hostels.json` on disk stayed unmodified. Notable results: WhatsApp bonus (+8) correctly
outranked other social signals as designed; `solo_group_ratio` correctly replaced (not
double-counted with) the old guest-type text heuristic when present; real `free_breakfast` data
correctly took priority over the fake `diy_breakfast_available` fallback wherever both existed.

Also found via this run: `score_split_period()` (the day/night split scoring helper) had a
cosmetic wording bug — a hostel scoring exactly `0` points (a genuinely neutral table entry, e.g.
`prefer_quiet`'s "low" = 0) fell into the same `else` branch as real negative-point mismatches,
so it was labeled "heads up: ... doesn't closely match" even though nothing was actually wrong.
Fixed by adding a distinct `bonus == 0` branch with neutral wording ("is a neutral match... —
neither close nor a mismatch"). The identical pattern existed in the original single-mode
`party_preference` fallback right below it (same "else: heads up" catch-all) and was fixed the
same way for consistency, even though it hadn't yet been hit in a live test. Verified directly by
re-running `validate.py daynight`: the neutral case (Vietnam Backpacker Hostels, daytime "low")
now shows the corrected wording, while a genuine mismatch (WanderThirst, daytime "medium" / -5)
still correctly shows "heads up." Purely cosmetic — no score values changed, only breakdown text.

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

### 🟡 PARTIALLY RESOLVED — A nuanced dual-mode query ("focus during the day, meet people at dinner") got ranked purely by party_level, ignoring the work/focus half entirely
Found via Task #6 validation. Query: "somewhere I can focus during the day but still meet people
over dinner." Claude's intent parser collapsed this into a single `party_preference: "prefer_
social"` value — the schema has no way to represent "quiet mornings, social evenings" as two
separate signals — and every one of the top-ranked results won purely on `party_level` closeness to
that single target (up to 20 points), with **zero** breakdown entries referencing remote work,
coworking, or focus at all. Confirmed this isn't just under-weighting: re-running with a reworded
query ("...focus **in work** during the day...") produced an almost identical parsed intent and,
critically, the same structural gap — the work/focus dimension of the query is not represented
anywhere in final ranking, regardless of phrasing.

**Direct product follow-up correctly reframed both halves as multi-field combinations, not single
tags**: "work focus" isn't one fact — it's wifi strength + a calm/AC'd place to sit + coffee + easy
commuting; "meet people over dinner" isn't a party-hostel question — it's guest-mix (solo vs.
group-heavy) + organized social activities + staff warmth + a *gentle* social read distinct from
raw party intensity. Checked the schema directly before building anything: `good_for_remote_work`
(already scored, step 7), `near_metro`/`near_airport`, and `kitchen_food.free_tea_coffee` exist for
the work-focus side; wifi quality, desk/seating setup, and common-area AC do NOT (confirmed —
`facilities.lounge_has_ac` is populated for only 4/226 hostels, "wifi" appears anywhere in free
text for only 11/226) — those went to the Field/Feature Backlog rather than being faked. For the
social side, `guest_type`, `social_activities`/`weekend_activities`, and `staff.friendliness` exist
and are decent signal; a dedicated communal-dinner/family-meal flag does not (only 12/226 mention
"dinner" anywhere) — also backlogged.

**Fixed with two new steps** (12→17 daytime work-focus combo, 18 evening social-mixing combo, added
directly after the curfew step): step 17 adds keyword-gated bonuses for commute ease (+4) and free
coffee (+3) on top of step 7's existing `good_for_remote_work` bonus (deliberately not repeated, to
avoid double-counting); step 18 adds a genuinely separate "social mixing probability" score —
solo-traveler-heavy guest mix (+5), group-heavy guest mix (-5, since group travelers tend to stick
together rather than mix with strangers), organized social activities naming a real example (+6),
friendly staff (+3), and a gentle light-to-medium party_level credit (+4) distinct from the raw
party-preference match in step 8. Verified live: the same "focus during the day... meet people over
dinner" query now shows real, non-zero breakdown entries for both halves (e.g. "free tea/coffee
available, handy for work sessions" + "organizes social activities (e.g. nightly pub crawl)" +
"popular with solo travelers") where before there were none.

**Still not fully resolved** — the underlying root cause (a single `party_preference` field can't
express time-varying preferences, and its point budget still tends to dominate the additive total)
is unchanged; today's fix adds real credit for the previously-invisible dimension without
rebalancing the overall weights or restructuring the intent schema. Top-ranked results for this
query still skew toward high-party_level hostels, just with more complete (and honest) reasoning
attached now. A full fix would need either splitting "daytime vibe"/"evening vibe" into separate
intent fields or a deliberate score-weight rebalancing pass — both real design work, not done here.

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

### 🟢 RESOLVED (pilot) — Thailand + India research pass: bed bugs, lockers, hair dryer, drying,
### curfew, plus new nearby-attraction research for the 15 gap hostels
Before committing to the full 228-hostel research pass, ran it first as a pilot on all 68
Thailand + India hostels (26 + 42), specifically to get real numbers on cost/effort and — just as
important — how often this kind of research actually finds a real answer versus correctly returning
null. Executed via 14 parallel `Agent` subagents (~5 hostels each, genuine `WebSearch`/`WebFetch`
calls, not the cheap Haiku-only pattern used for `views`/`party_level`/nearby-restructuring above),
batched by hostel so each subagent could research every applicable field per hostel from the same
source material in one pass.

New fields added to `services`: `bed_bug_reports` (bool|null), `lockers` ({available, type, note}),
`hair_dryer_available` (bool|null), `clothes_drying_facility` (bool|null), `curfew_policy`
(string|null) — plus `research_sources.pilot_2026_08_thailand_india` per hostel (the actual URLs
used) for auditability. `location.nearby` was also populated from scratch (same structured shape as
`normalize_nearby_and_boutique.py`) for the 15 of these 68 hostels that had no existing nearby data.

**Coverage results (68 hostels)** — this is the actual reliability signal the pilot was for:
- `curfew_policy`: 47/68 (69%) populated — high coverage, since check-in/reception hours are almost
  always stated on OTA listings even when a hostel calls itself "no curfew."
- `lockers.available`: 41/68 (60%) confirmed `true`, 0 confirmed `false`, 27 (40%) null — makes
  sense: a hostel having lockers gets mentioned, a hostel NOT having them almost never does (nobody
  writes a review just to say "no lockers"), so `false` will stay rare across this whole dataset by
  the nature of the source material, not a research gap.
- `bed_bug_reports`: 34/68 (50%) confidently `false` (reviewed, no credible signal), 6/68 (9%)
  `true` (a real, credible report found), 28/68 (41%) null (not enough review signal to judge either
  way). The 6 `true` hits are the most important number here — one of them (The Habitat Hostel Koh
  Chang) independently corroborates a bed-bug mention already sitting in that hostel's
  `flagged_issues` from the original research pass, a genuine cross-check that the new research is
  finding real signal, not noise.
- `hair_dryer_available` and `clothes_drying_facility`: the weak spots — only 10/68 (15%) and 8/68
  (12%) came back `true` respectively, with 81-85% null. These are rarely stated explicitly on
  listings or in reviews, so a high null rate here is an honest finding about the source material,
  not a failed search — expect this to hold across the full 228.

**Effort observed**: ~862K total tokens and 391 tool calls across all 14 subagents (~12.7K
tokens/hostel), run in parallel so real wall-clock was a few minutes rather than the ~23 minutes of
summed agent-time. Extrapolating linearly to the remaining 160 hostels: roughly 2.4x this pilot's
token/tool-call volume, run as ~30-35 more subagent batches. Exact dollar cost isn't something this
project has visibility into (depends on the account's billing rate), but the effort scale is now a
real, measured number instead of a guess.

**Decision on how to proceed with the remaining 160 hostels**: given the sparse coverage on hair
dryer/drying facility specifically, worth deciding up front whether to keep researching those two
fields at the same depth (accepting an ~85% null rate) or deprioritize them for the remaining
countries and focus research effort on the two fields that actually turned up usable signal
(curfew, lockers) plus bed bugs (safety-relevant even at a 50/9/41 split) and new nearby-attraction
research. Not yet decided — flagged here for the next planning conversation.

### 🟢 RESOLVED — Consolidated the 3 validate_*.py scripts and 2 synthetic fixture files into one toolkit
Same proliferation problem as the earlier data-enrichment scripts (see the `data_tools.py`
consolidation entry below), spotted directly: `validate_semantic_matching.py`,
`validate_daynight_split.py`, and `validate_backlog_fields.py` were each written one at a time in
response to whatever validation need came up in the moment, with `test_fixtures/
synthetic_daynight_test.json` and `test_fixtures/synthetic_backlog_fields_test.json` accumulating
the same way. Replaced with `validate.py` (mirrors `data_tools.py`'s registry pattern — a `SUITES`
dict mapping a name to a run function, selected via `python validate.py <suite>`, with `all`
running every suite) and a single `test_fixtures/synthetic_test_data.json` holding both fixtures
under separate top-level sections (`daynight`, `backlog_fields`), so nothing about a future
validation need requires a new file — just one new function + one registry entry, or one new
top-level section in the fixture file if it needs fake data. Verified the consolidation reproduces
identical output: re-ran both fixture-based suites (`daynight`, `backlog_fields`) through the new
single entry point and confirmed the same before/after breakdowns and the same "hostels.json
unmodified" sanity-check result as the original separate scripts.

### 🟡 TECH DEBT — 7 more backlogged fields brought forward the same way: schema + scoring logic built and validated now, real research deferred; plus a new field (WhatsApp community group)
Direct follow-up, same reasoning as the daytime/evening split entry directly below: rather than
waiting for a full research pass to touch `matching.py` at all, pulled the rest of the
Field/Feature Backlog forward into real schema + real scoring logic now, validated against a
second synthetic fixture — genuine research on the actual values remains deferred and tracked
below, not done here. Also added a brand new field, raised directly: **`whatsapp_community_group_
available`** — the observation was that an active WhatsApp/community group is the actual mechanism
by which a hostel's guests coordinate hangouts/day-plans/group activities, and is part of why
travelers often return to the same hostel on a later trip (they're still in the group). Agreed this
is a genuinely distinct, strong signal — not just another "organizes activities" data point — so it
carries the highest single bonus (+8) in the evening social-mixing step, above generic activities
(+6) and communal dinners (+6).

**Fields added, all as real schema + real `matching.py` scoring, all EXPERIMENTAL (no real hostel
has values yet)** except `free_breakfast` which turned out to already be real data (37 true / 19
false / 226 total in the actual dataset) and is now wired for real, no fixture needed:
- `facilities.wifi_quality` / `facilities.desk_setup` — extends the daytime work-focus combo
  (step 17).
- `kitchen_food.diy_breakfast_available` / `kitchen_food.kitchen_utensils_quality` — new step 19
  (food self-sufficiency combo), alongside the now-real `free_breakfast`.
- `social_vibe.communal_dinner_available` / `social_vibe.whatsapp_community_group_available` /
  `social_vibe.solo_group_ratio` — extends the evening social-mixing combo (step 18);
  `solo_group_ratio` takes priority over the older `guest_type` text heuristic when present, falls
  back to the original heuristic otherwise so real hostels (which only have `guest_type` today)
  are unaffected.

**Validated the same way as the daytime/evening split** — NOT by writing fake values into
`hostels.json` (rejected for the same reason as before: real production data must never carry
fabricated values, even flagged ones). Built `test_fixtures/synthetic_backlog_fields_test.json`
(26 hostels, `random.seed(99)`, explicit `_WARNING`) and `validate_backlog_fields.py`, which
deep-copies the real hostel list, overlays the synthetic values onto the copy only, and runs 3
test queries (one per new/extended step) against both real and synthetic-overlay data. Verified
live: all 3 cases show the new fields contributing real, correctly-labeled breakdown entries in
the "after" run and nothing in "before" (since real data is null), and the closing sanity check
confirms `hostels.json` on disk is byte-identical before and after. The food-self-sufficiency test
case incidentally also confirms `free_breakfast` (the one real field in this batch) was already
working correctly even before today's changes.

**Not done here**: any real per-hostel research for these 7 fields. See Field/Feature Backlog below
for the updated entries.

### 🟡 TECH DEBT — Fix B (daytime/evening intent split) implemented and mechanically validated against synthetic data; real hostel-side research not started
Direct follow-up to the "focus during the day, meet people over dinner" dual-mode gap (see the
PARTIALLY RESOLVED entry above). Decided to pursue "Fix B" (split intent fields) over "Fix A"
(rebalance party_preference's point weights) — Fix A is cheap but blunt (it would've changed every
other query's party scoring, not just dual-mode ones); Fix B is more correct but real work.

**What was built:**
1. `main.py`'s `parse_intent()` prompt gained two new optional fields, `daytime_vibe_preference`
   and `evening_vibe_preference` (each `"quiet"`/`"social"`/null), only set by Claude when a query
   genuinely names two different times of day with two different vibes — explicit few-shot examples
   included in the prompt to keep this from over-firing on ordinary single-mode queries.
   `party_preference` is always still filled the same way regardless, as the fallback.
2. `matching.py`'s party-scoring step now branches: if either new field is set, it runs a NEW
   split-scoring path (two halved score tables, one per period, reading
   `social_vibe.daytime_party_level`/`evening_party_level`) instead of the original single-mode
   `party_preference` table — never both, to avoid double-counting the same underlying signal.
3. **The hostel side does NOT have real `daytime_party_level`/`evening_party_level` data.** Every
   real hostel in `hostels.json` has these as null/missing — that needs genuine new research
   (per-hostel, likely from reviews mentioning "quiet during the day, lively at night" type
   language), same research-cost category as the bed-bugs/lockers pass, NOT done here. Added to the
   Field/Feature Backlog below.

**How the logic was validated anyway, without fabricating real data**: rather than randomly filling
these two fields into `hostels.json` itself (rejected — even clearly flagged, fake values living in
the same file real search results are served from is a real risk if a flag gets missed later), built
a separate `test_fixtures/synthetic_daynight_test.json` (23 hostels, `random.seed(42)`, explicit
`_WARNING` field, values independent of each hostel's real `party_level` on purpose — the goal is
stress-testing the scoring math itself, not simulating realistic hostels) plus
`validate_daynight_split.py`, which deep-copies the real hostel list in memory, overlays the
synthetic values onto the copy ONLY, runs the same dual-mode query against both the untouched real
data ("before" — everything reads as "not researched yet") and the synthetic-overlay copy
("after"), and ends with an explicit sanity check confirming `hostels.json` on disk is byte-identical
before and after the run. Verified live (real Claude call — Voyage still unreachable from this
sandbox, doesn't matter here since this test doesn't depend on semantic scoring): the parser
correctly detected the split (`daytime_vibe_preference: "quiet"`, `evening_vibe_preference:
"social"`, `party_preference: "neutral"` — correctly NOT double-set), the split-scoring branch fired
instead of the single-mode branch, and rankings shifted sensibly based on the fake data (e.g. a
hostel with synthetic `daytime: low, evening: high` correctly scored well for this query). This
proves the scoring mechanism is correct; it says nothing yet about real-world ranking quality, since
production data for these two fields doesn't exist.

**Next step, not done here**: genuine research pass to populate
`daytime_party_level`/`evening_party_level` for real hostels (probably starts with the ones most
likely to have day/night contrast — coworking-forward or "chill by day, social by night" branded
properties), same batched-Agent-subagent pattern as the services-field research passes above.

### 🟢 RESOLVED — New services-field keyword matching silently failed because it only checked parsed vibe_tags, not the raw query
Found via Task #6 validation (`validate_semantic_matching.py`), which had 2 new test cases added
specifically to probe the just-wired bed-bug/lockers/hair-dryer/drying/curfew scoring (steps 12-16
above). Both new cases immediately exposed a real bug on their first live run: a query for "secure
lockers" parsed into vibe_tags `["clean", "comfortable", "secure", "safe", ...]` — the literal word
"lockers" never survived Claude's paraphrasing — so the lockers step's keyword check (which only
looked at `vibe_tags`) never fired despite the traveler explicitly asking for lockers. Same failure
for "hair dryer... dry my clothes", which parsed into `["practical amenities", "laundry"]` with
neither "hair dryer" nor "drying" anywhere. This is a different failure mode from the existing
transit/remote-work/boutique steps (which happen to use common-enough words that survive
paraphrasing) — these 5 fields are specific factual asks where literal wording matters, and
paraphrase-tolerant tag matching actively works against that. **Fixed** by adding `raw_query` as an
optional parameter threaded through `score_hostel()` (already available in `match_hostels()` for
semantic matching, just not passed down before) and having the 5 new keyword checks search a
combined `vibe_tags + raw_query` text blob instead of `vibe_tags` alone. Re-verified live (real
Claude + Voyage calls, not simulated) immediately after the fix: both cases now correctly surface
the lockers/hair-dryer/drying/curfew bonuses. General lesson, same shape as several earlier ones in
this log: a fix validated on one field doesn't automatically generalize — worth deliberately
testing new scoring logic with real queries before considering it done, exactly what Task #6's
validation script exists for.

### 🔴 CORRECTION — the 2026-08-28 "live" validate_semantic_matching.py run did NOT actually test the semantic layer; Voyage is unreachable from this environment
An earlier version of this entry claimed the "calm surroundings" case was re-tested live and
showed no semantic contribution in the top 5. That claim was wrong and has been replaced by this
entry. Root cause, caught directly when double-checking: this sandbox's network egress reaches the
Anthropic API fine (confirmed — `parse_intent()` calls genuinely succeeded), but cannot reach
`api.voyageai.com` at all (`ProxyError('Unable to connect to proxy', OSError('Tunnel connection
failed: 403 Forbidden'))`, confirmed via a direct `embed_query()` call). `compute_semantic_entries()`
is deliberately written to degrade gracefully and silently skip the semantic bonus on ANY exception
(see its docstring — "semantic matching is a bonus layer, not a hard dependency"), which is the
right behavior for production but means every "live" validation run done from this environment,
including all 8 cases in the 2026-08-28 run, executed with the semantic layer silently disabled
the whole time. The parsed intents and structured-scoring breakdown entries from that run are real
and valid (that's how the genuine raw_query/paraphrasing bug above was found), but nothing about
semantic similarity was actually exercised — the absence of `semantically matches` entries in those
results is an artifact of the environment, not a product finding. **Still needed to close Task #6**:
someone needs to actually run `validate_semantic_matching.py` (or the live `/search` endpoint)
somewhere Voyage is reachable — i.e. not this sandbox — the same way the semantic embeddings
themselves were originally generated and Voyage was validated back in Task #3/#4. Same
infrastructure limitation as earlier in the project (Voyage AI calls have always needed to run
from outside this sandbox, not something new).

### 🟢 RESOLVED — 160-hostel research pass completed (light-touch), 7 data-quality issues found and fixed, 5 new fields wired into matching
Follow-up to the pilot (Thailand+India, 68 hostels — see above): ran the same bed
bugs/lockers/hair-dryer/drying/curfew/nearby research across the remaining 160 hostels, split
into two ~40-hostel chunks with a pause between them (token-budget concern), using a
LIGHT-TOUCH methodology (1-2 targeted searches per hostel instead of the pilot's deeper
multi-source dive) per direct request — "not this much deep research is needed at this phase of
product development." This traded some coverage depth for roughly 2-3x less effort per hostel,
while keeping all 5 fields (rejected the alternative of dropping hair dryer/drying despite their
weak pilot yield, since consistency across the dataset was preferred over maximizing yield on 3
fields at this stage). Result: all 158 non-Thailand/India, non-pilot hostels researched across 13
parallel `Agent` subagent batches with zero WebSearch budget exhaustion this time (the light-touch
depth stayed well under the per-session quota that caused Wave 2 failures in an earlier attempt at
this same pass) — each batch wrote its own results file immediately (`research_batches/
remaining_160_wave1.json` + `remaining_160_wave2_batch{1-12}.json`) specifically so a later
failure couldn't lose earlier work, a direct lesson from that earlier quota-exhaustion incident.

**Data-quality issues surfaced during research** (same "flag, don't fabricate" discipline as the
pilot): 7 total. 5 were city/location mix-ups, fixed directly in `hostels.json` (city/region
corrected, `source_note` updated with a dated correction note): Roy's Villa Hostel (#67,
Unawatuna → Sigiriya), Camp Poe (#71, Ella → Ahangama), Montacute Boutique Bunkhouse (#144,
Adelaide → Hobart), Kamasanti Hostel (#116, Sanur → Nusa Penida), and Greg & Tom Hostel Krakow
(#130, ambiguous which of several similarly-branded Krakow properties — left as-is with a note,
since 100% correctness isn't the bar at this stage). 2 were "does this listing even belong in the
dataset" questions rather than typos, and were **removed entirely** after explicit confirmation:
Maverick Hostel Budapest (#80, completely unreachable in research — no listing found on any
platform) and Selina Valparaiso (#178, the Selina chain has reportedly closed most of its
properties and this specific one couldn't be confirmed still open). Dataset is now 226 hostels
(228 - 2 removals). All per-hostel research notes (38 of them — data-quality flags, single-source
caveats, budget-tool-limit caveats, etc.) were preserved into each hostel's `source_note` rather
than silently discarded when merged, even though they don't map to any structured field.

**Final coverage across all 226 hostels** (pilot + both waves combined): `location.nearby` 222/226
(98%); `services.lockers.available` 138 true / 3 false / 85 null; `services.bed_bug_reports` 13
true / 76 false / 137 null; `services.curfew_policy` 112/226 (50%) populated;
`services.hair_dryer_available` 45 true / 5 false / 176 null; `services.clothes_drying_facility`
38 true / 5 false / 183 null — hair dryer and drying stayed the two weakest fields across the full
dataset exactly as the pilot predicted, confirming that was real signal about the source material,
not a fluke of the smaller pilot sample.

**Wired into `matching.py` scoring** (steps 13-17, added directly after this merge completed — the
pilot's equivalent fields had been sitting collected-but-unused the same way `views`/`nearby` once
were, see the RESOLVED items above for that same category of gap): `bed_bug_reports` applies an
unconditional -15 penalty when true regardless of query wording (treated as a real dealbreaker-
class safety signal, not a mere preference — same reasoning as why `flagged_issues` severity
always matters), with a smaller keyword-gated +6 bonus for confirmed-clean only when the traveler
actually raised safety/cleanliness themselves. `lockers`, `hair_dryer_available`, and
`clothes_drying_facility` are keyword-gated (score only when the query mentions them), +6/+8 if
confirmed present, -4/-5 if confirmed absent, silent if unknown — same pattern as the existing
transit/remote-work/boutique steps. `curfew_policy` is keyword-gated on curfew/late-access
language, interpreted as "wants flexibility" (the far more common real intent behind this phrasing)
— no-curfew/24hr language scores +8, a real curfew scores -8. Verified live against sample queries
for each field before considering this done.

### 🟢 RESOLVED — Consolidated all one-off data-enrichment scripts into a single reusable toolkit
Raised directly by the traveler: `normalize_views.py`, `reclassify_party_level.py`,
`normalize_nearby_and_boutique.py`, and `merge_pilot_research.py` were four separate files that each
did real, useful work, but writing a brand new script for every future field/pass was never going to
scale — schema growth is the whole shape of this project going forward.

Replaced with `data_tools.py`, which splits the real underlying pattern into two reusable, generic
operations instead of one script per task:

1. **`normalize <task>`** — re-reads a hostel's own existing fields via Claude Haiku and
   reclassifies/restructures them (no new research). What all three normalize-style scripts were
   doing. Each task (`views`, `party_level`, `boutique_nearby`) is now a small entry in a
   `NORMALIZE_TASKS` registry (filter/system-prompt/context/apply) instead of a whole file — adding
   a future normalization pass means adding one dict entry, not a new script.
2. **`merge <results.json> --batch-name <name>`** — applies already-gathered research (e.g. from
   Agent subagents doing real WebSearch/WebFetch) into `hostels.json`. What `merge_pilot_research.py`
   did, except that script hardcoded the Thailand+India results directly as a Python literal, which
   meant the next country batch would've needed another near-duplicate file. Research results now
   live as plain JSON under `research_batches/` (e.g. `research_batches/thailand_india_2026_08.json`
   holds the actual pilot data), and `merge` applies any such file via a `MERGE_FIELD_MAP` — a new
   field from a future research pass needs one line added to that map, not a new script.

Verified the consolidation reproduces identical results: re-ran `merge` against the already-applied
pilot data and confirmed every field value matched exactly (only difference was a duplicate
`research_sources` key from testing with a different `--batch-name`, reverted — not a real
discrepancy).

**This directly answers "which file will the remaining 160-hostel pass update"**: none of the
old task-specific scripts — future research batches produce a results JSON file (same shape as
`research_batches/thailand_india_2026_08.json`), and `data_tools.py merge` applies it. The four old
scripts are removed; their already-applied effects remain in `hostels.json` as before (nothing needs
to be re-run).

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
