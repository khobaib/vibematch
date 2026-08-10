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
