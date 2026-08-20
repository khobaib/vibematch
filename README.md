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
- **A real matching engine** — scores a hand-curated database of 228 hostels across 40 countries
  against that intent, with hard constraints (location) kept separate from soft ranking signals
  (budget, vibe) — a distinction that took real product judgment to get right, documented below.
  Every point in the final score is individually auditable, never an opaque number.
- **AI-generated "why we matched this" explanations** — a second Claude call turns the raw score
  breakdown into a scannable verdict + highlights + heads-ups format, honest by design (a weak or
  mismatched result says so plainly instead of being spun positive), including calibrated
  disclosure of genuine flagged safety/quality issues from past guest reports
- **A React frontend, connected end-to-end to the real backend** — live search, live scoring,
  live AI explanations, with proper loading/error/data states and a custom "boarding pass /
  travel stamp" visual design system

```
User query → Claude intent parser → matching engine → ranked results + reasons → AI explanation
```

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
| AI | Claude (Anthropic API) — intent parsing, structured extraction, AI-generated match explanations |
| Frontend | React, Vite |
| Data | Hand-curated JSON dataset (228 hostels, 40 countries), migration path to PostgreSQL planned |

Hands-on across the full stack was a deliberate choice, not incidental — it's the fastest way I
know to pressure-test a product idea against reality instead of a slide.

---

## Status

The core loop is live and working end-to-end: real query → real intent parsing → real matching
against 228 hostels → real AI-generated explanations, all connected through an actual frontend,
not mocked data. ~18-20 real bugs were found and fixed through deliberate adversarial testing
before this was considered stable (full list in the decision log).

**Actively being extended right now:**
- **Semantic vibe matching** — replacing pure text/substring vibe-tag matching with
  embeddings-based similarity, so a query like "calm surroundings" correctly matches a hostel
  tagged "quiet" instead of scoring zero for not sharing literal text. A known, self-diagnosed
  limitation being fixed deliberately, not discovered by a user.
- **An automated eval suite** — turning the ~20 adversarial test cases already documented in the
  decision log into a repeatable regression suite, so future prompt/scoring changes can be
  checked automatically instead of only by hand.
- **Native structured outputs** — moving intent parsing and explanation generation off manual
  JSON-string parsing onto Claude's tool-use/forced-schema output for guaranteed-valid responses.

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

You'll need an `ANTHROPIC_API_KEY` in a `.env` file inside `backend/`.

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
