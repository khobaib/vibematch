# VibeMatch 🎒

**AI-powered hostel discovery — describe the vibe you want, get matched stays with real explanations.**

VibeMatch is a conversational search layer for hostel travel, built on a simple product insight:
"budget, cleanliness, social score" filters miss almost everything that actually makes or breaks
a stay. Instead of checkboxes, travelers describe what they want in plain language — *"quiet
hostel near a metro station, good for a long stay, solo backpacker"* — and get ranked results
with clear, honest reasons for every match.

> A product built end-to-end — problem discovery, requirements, data modeling, and working
> software — to demonstrate how I use AI tools to move from idea to shipped product as a PM,
> not just to write specs about it.

---

## The Problem

Booking platforms reduce every hostel to the same handful of filters, while the things that
actually decide whether a trip goes well — *is the pool actually open this season, is there
construction noise, is the walk from the bus stop safe at night* — are buried in scattered
reviews nobody has time to read.

This started as user research, not a spec: two Medium articles diagnosing the problem from 70+
personal hostel stays across Asia and Europe, which then became the requirements for this build.
- [Rethinking Travel Booking Filters: A Traveler's Perspective](https://medium.com/@khobaib/rethinking-travel-booking-filters-a-travelers-perspective-d503be509968)
- [Beyond Filter: How Democratizing Data Could Revolutionize Travel Apps?](https://medium.com/@khobaib/beyond-filter-how-democratizing-data-could-revolutionize-travel-apps-2a2420e54fd6)

---

## What's Built

- **Conversational intent parsing** — a FastAPI backend uses Claude to turn a free-text query
  into structured product data (location, budget, vibe, traveler type), including *inferred*
  signals a naive keyword search would miss — e.g. reading "wants to shop at the local market"
  as a signal for a longer stay, not just a tourist visit
- **A real matching engine** — scores a hand-curated database of 226 hostels across 40+ countries
  against that intent, with hard constraints (location) kept separate from soft ranking signals
  (budget, vibe) — a distinction that took real product judgment to get right, documented below.
  Every point in the final score is individually auditable, never an opaque number.
- **Semantic vibe matching, powered by a second model (Voyage AI)** — Claude writes a
  natural-language "vibe profile" for every hostel, Voyage embeds it, and the traveler's query is
  embedded and compared the same way at search time — so "calm surroundings" correctly surfaces a
  hostel tagged "quiet" instead of scoring zero for not sharing literal text. Degrades gracefully
  to structured-only scoring if the embedding service is ever unreachable — never breaks search.
- **Real-world services scoring** — bed bug safety signals, lockers, hair dryer availability,
  clothes-drying facilities, and curfew policy (with a sharper penalty for a real curfew when the
  traveler explicitly needs 24/7 access) all feed into ranking, sourced from a dedicated research
  pass across the full dataset.
- **AI-generated "why we matched this" explanations** — a second Claude call turns the raw score
  breakdown into a scannable verdict + highlights + heads-ups format, honest by design (a weak or
  mismatched result says so plainly instead of being spun positive), including calibrated
  disclosure of genuine flagged safety/quality issues from past guest reports
- **Reliable structured AI output** — both the intent parser and the explanation generator use
  Claude's forced tool-calling (a JSON Schema per call), not manual "please respond with JSON"
  prompting — the API itself guarantees valid, schema-conforming output.
- **An automated regression eval suite** — 16 test cases seeded directly from real bugs found and
  fixed during development, run as pass/fail assertions (not manually re-read breakdowns) so a
  future change can't silently reintroduce a bug that was already caught once.
- **A React frontend, connected end-to-end to the real backend** — live search, live scoring,
  live AI explanations, with proper loading/error/data states and a custom "boarding pass /
  travel stamp" visual design system

```
User query → Claude intent parser (forced tool-calling) → matching engine
  (structured scoring + Voyage semantic similarity) → ranked results + reasons
  → Claude explanation (forced tool-calling)
```

---

## AI/LLM Engineering Highlights

This project exists as much to demonstrate hands-on AI/LLM engineering as to be a working product
— every item below is implemented and running, not a slide.

- **Prompt engineering as an iterative, testable discipline** — the intent-parsing prompt was
  built through direct before/after evaluation on real queries, not written once and trusted;
  explicit rule-teaching (few-shot-style examples, inference heuristics) closed real gaps a
  generic prompt missed.
- **Structured output / tool-calling, not string-parsed JSON** — both LLM calls (intent
  extraction, match explanation) use Claude's forced tool-calling with a defined JSON Schema per
  call, replacing an earlier "ask nicely for JSON + regex-strip markdown fences" approach. The API
  itself now guarantees schema-conforming output.
- **Multi-model orchestration** — Claude (reasoning/generation) and Voyage AI (embeddings) are
  used together deliberately, each for what it's actually good at, rather than forcing one model
  to do everything. Includes designed-in graceful degradation: if the embedding service is
  unreachable, search still works, just without the semantic bonus layer — verified directly, not
  assumed.
- **Retrieval via embeddings / semantic similarity** — hostel "vibe profiles" (themselves
  LLM-generated from structured data) are embedded and compared against query embeddings via
  cosine similarity at search time, the same core mechanism behind RAG-style retrieval systems,
  applied here to solve a real semantic-matching gap in production scoring logic.
- **An automated LLM-system eval suite** — 16 regression test cases, seeded from real bugs found
  during development, run as automated pass/fail assertions across three tiers (deterministic
  logic / live-LLM / live-LLM-plus-embeddings) so changes to prompts or scoring can be verified
  without manual re-inspection every time — genuine eval-harness discipline, not just "it looked
  right when I tried it."
- **Cost- and reliability-aware LLM usage** — rate-limit-aware batching for the one-time embedding
  generation job, silent-exception-swallowing designed deliberately (so an optional AI layer never
  takes down core search), and honest tracking of real, environment-specific failure modes (e.g.
  one deployment environment can reach the reasoning model but not the embeddings provider — see
  the decision log for how that was diagnosed and worked around, not glossed over).
- **A running decision log treating every AI-behavior discovery as a real finding** — non-
  deterministic LLM output, prompt drift, paraphrasing side effects, and a self-caught incorrect
  claim about what had actually been tested live are all documented and corrected in the open,
  the same rigor expected of a PM working with AI systems in production.

---

## How I Worked — Product Decisions, Not Just Code

The most PM-relevant part of this repo is [`DECISIONS_LOG.md`](./DECISIONS_LOG.md) — a running
decision log kept from day one, structured like an early-stage PRD's changelog: every product
and technical choice, the reasoning behind it, and every known tradeoff or piece of debt, tracked
openly rather than hidden once the code "works."

A few examples of the judgment calls captured there:

- **Requirements discovery through iteration, not one-shot design.** Early versions of the intent
  parser produced shallow output (`["solo", "backpacker"]`). Rather than accept that, I treated it
  like a requirements-gathering problem — explicitly encoding domain knowledge from my own travel
  history into the AI's instructions — and validated the improvement with direct before/after
  comparison on real queries, the same way I'd validate a feature change with real usage data.
- **Deciding what should be a hard rule vs. a ranking preference.** Location and budget look
  similar at first glance, but I deliberately made location a hard filter (a Cambodia hostel is
  never useful for a Goa search, no exceptions) while keeping budget a soft signal (a traveler
  might flex $3 over budget for the right place). Getting this distinction wrong was a real bug I
  found through testing, not a hypothetical — logged with full reasoning.
- **Treating AI-generated data as a hypothesis, not a fact.** Every hostel entry carries a source
  note documenting what was searched and how confident the data is, and several entries were
  corrected after conflicting with my own firsthand experience — the same skepticism I'd apply to
  any third-party data source in a real product.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI |
| AI — reasoning | Claude (Anthropic API) — intent parsing and match explanations, via forced tool-calling for guaranteed structured output |
| AI — semantic search | Voyage AI (`voyage-4`) — vibe-profile embeddings + query embeddings for semantic similarity matching, independent of Claude |
| Frontend | React, Vite |
| Data | Hand-curated JSON dataset (226 hostels, 40+ countries), migration path to PostgreSQL planned |
| Validation | Custom, dependency-free: `validate.py` (human-readable inspection) + `eval_suite.py` (automated pass/fail regression suite) |

Hands-on across the full stack was a deliberate choice, not incidental — it's the fastest way I
know to pressure-test a product idea against reality instead of a slide.

---

## Status

The core loop is live and working end-to-end: real query → real intent parsing → real matching
against 226 hostels → real AI-generated explanations, all connected through an actual frontend,
not mocked data. Dozens of real bugs were found and fixed through deliberate adversarial testing
(full list in the decision log), and the most safety/correctness-critical ones are now locked in
as permanent automated regression tests, not just fixed once and hoped to stay fixed.

**Recently shipped:**
- **Semantic vibe matching** — a second model (Voyage AI) compares query meaning against each
  hostel's AI-written vibe profile via embeddings, so "calm surroundings" correctly matches a
  hostel tagged "quiet" instead of scoring zero for not sharing literal text.
- **An automated eval suite** (`eval_suite.py`) — 16 regression test cases seeded from real,
  previously-fixed bugs in the decision log, run as automated pass/fail assertions across three
  tiers (no API calls / live Claude / live Claude + Voyage) rather than checked by hand.
- **Native structured outputs** — intent parsing and explanation generation now use Claude's
  forced tool-calling for guaranteed-valid JSON, replacing manual markdown-stripping and
  `json.loads()`.
- **Real-world services data** — bed bug reports, lockers, hair dryer/drying facilities, and
  curfew policy, sourced from a dedicated research pass and wired into scoring with
  safety-critical fields (bed bugs) scored unconditionally rather than only when asked about.

**Being actively explored (built, but on synthetic test data pending real research):**
- **Daytime/evening split preference** — separate scoring for queries like "focus during the day
  but meet people over dinner," where a single overall party-preference field can't represent two
  different vibes across one stay. The scoring logic is real and tested; the hostel-side data
  (`daytime_party_level`/`evening_party_level`) doesn't exist for any real hostel yet.
- A small backlog of similar fields (wifi quality, desk setup, DIY breakfast, WhatsApp community
  groups, and others) — same pattern: real schema and scoring logic, validated against clearly-
  labeled fake test data, real per-hostel research tracked openly as a backlog rather than rushed.

**Not yet built:** public deployment/hosting, real OTA data integration (live pricing/availability
from Hostelworld/Booking.com — outreach in progress, both require partner approval rather than a
self-serve API key), and user accounts (out of scope for this stage) — each scoped and reasoned
through in the decision log, not left as a bare TODO.

See [`DECISIONS_LOG.md`](./DECISIONS_LOG.md) for the full record.

---

## Getting Started

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

You'll need `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` in a `.env` file inside `backend/` (Voyage
powers the semantic vibe-matching layer — the app still runs without it, just without that
bonus scoring layer, since it's designed to degrade gracefully).

---

## About the Builder

Built by [Khobaib Chowdhury](https://www.linkedin.com/in/khobaib-chowdhury-554a104/) — Senior
Product Manager with engineering background, specialising in marketplace and operations-heavy
products. This project is part of a broader effort to demonstrate AI-tool collaboration patterns
I'd use in a senior PM role.

Open to senior PM opportunities — [khobaib@gmail.com](mailto:khobaib@gmail.com).

---

## License

MIT — see [LICENSE](./LICENSE).
