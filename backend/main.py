import os
import json
import logging
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from matching import load_hostels, match_hostels
from semantic_similarity import load_hostel_embeddings

load_dotenv()

app = FastAPI()

# Basic abuse/cost protection (added once the live demo started being shared
# aggressively - see DECISIONS_LOG.md). Both /search and /explain call a
# paid LLM API on every request, so an unthrottled endpoint is a real
# billing risk (a script or bot looping the same query costs real money,
# not just server load). This is a per-IP rate limit, not a full security
# solution - it stops the realistic case (one bot/one person hammering
# requests) but not a determined attacker rotating IPs. Good enough for
# this stage; a more serious defense (API keys, WAF, etc.) would only be
# worth the complexity once there's an actual paying business to protect.
#
# Fly.io terminates TLS at its edge and forwards the real client IP in the
# "Fly-Client-IP" header - without reading that header explicitly, every
# request would appear to come from Fly's internal proxy IP, and the limit
# would (incorrectly) apply globally instead of per real visitor.
def get_client_ip(request: Request) -> str:
    fly_client_ip = request.headers.get("Fly-Client-IP")
    if fly_client_ip:
        return fly_client_ip
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prompt-cache visibility (added alongside the caching change itself):
# Anthropic's Messages API returns cache_creation_input_tokens (set on the
# call that first writes the cache) and cache_read_input_tokens (set on any
# later call that hits it) inside message.usage. Without logging this,
# there's no way to actually confirm caching is working versus just hoping
# the code is correct - so every Claude call logs its usage line, visible
# in `fly logs` in production or the local uvicorn console in dev.
logger = logging.getLogger("vibematch.cache")
logging.basicConfig(level=logging.INFO)


def log_cache_usage(label: str, usage) -> None:
    logger.info(
        "[cache] %s | input=%s cache_creation=%s cache_read=%s output=%s",
        label,
        getattr(usage, "input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "output_tokens", None),
    )

# Allow the React dev server (different origin: localhost:5173 vs 127.0.0.1:8000)
# AND the deployed Vercel frontend to call this API. Without this, the
# browser blocks every request before it even reaches FastAPI - this is a
# browser security rule (CORS), not optional.
#
# Task #10 (DECISIONS_LOG.md): the production frontend origin is read from
# an env var (FRONTEND_ORIGIN) rather than hardcoded, since the real Vercel
# URL isn't known until after the first Vercel deploy. Set it via
# `fly secrets set FRONTEND_ORIGIN=https://your-actual-project.vercel.app`
# once you have that URL. Local dev origins stay allowed unconditionally so
# `npm run dev` keeps working without needing this env var set locally.
LOCAL_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
production_frontend_origin = os.getenv("FRONTEND_ORIGIN")
allowed_origins = LOCAL_DEV_ORIGINS + ([production_frontend_origin] if production_frontend_origin else [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Load hostels once at startup, not on every request
HOSTELS = load_hostels("hostels.json")
HOSTELS_BY_ID = {h["id"]: h for h in HOSTELS}

# Load precomputed vibe-profile embeddings once at startup too, for
# semantic matching (see matching.compute_semantic_entries). This is
# genuinely optional infrastructure: if hostel_embeddings.json hasn't
# been generated yet (or Voyage isn't reachable at request time later),
# search should still work — just without the semantic bonus score. Never
# let a missing/broken embeddings file take down the whole API.
try:
    HOSTEL_EMBEDDINGS = load_hostel_embeddings()
    print(f"Loaded {len(HOSTEL_EMBEDDINGS)} hostel vibe-profile embeddings for semantic matching.")
except Exception as e:
    HOSTEL_EMBEDDINGS = None
    print(f"WARNING: could not load hostel embeddings, semantic matching disabled: {e}")


def extract_tool_input(message, tool_name: str) -> dict:
    """
    Task #7 refactor (see DECISIONS_LOG.md): replaces the old extract_text()
    + manual markdown-fence-stripping + json.loads() pattern. Both
    parse_intent() and generate_explanation() now force a tool call with a
    JSON Schema, so Claude's API guarantees a schema-conforming dict back
    (message.content's tool_use block already has .input parsed) — no more
    depending on Claude choosing to obey a plain-English "respond ONLY with
    JSON" instruction, and no more risk of json.loads() throwing on
    malformed output.

    Still don't assume content[0] is the tool_use block, though — a forced
    tool call can still be preceded by a ThinkingBlock with internal
    reasoning (same reason extract_text() had to search rather than assume
    position). Search for the right block by type and name instead.
    """
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return block.input
    raise ValueError(
        f"No tool_use block for '{tool_name}' found in Claude's response. Content block types received: "
        f"{[getattr(b, 'type', type(b).__name__) for b in message.content]}"
    )


class SearchRequest(BaseModel):
    query: str


class BreakdownEntry(BaseModel):
    points: int
    reason: str


class ExplainRequest(BaseModel):
    intent: Dict[str, Any]
    hostel_id: int
    breakdown: List[BreakdownEntry]


@app.get("/")
def read_root():
    return {"message": "VibeMatch backend is alive"}


# Task #7 (DECISIONS_LOG.md): forced-tool-call schema for parse_intent().
# The reasoning instructions (traveler-profile inference rules, budget
# strict/approximate distinction, daytime/evening split examples, etc.)
# still live entirely in the prompt text below — this schema only
# constrains output SHAPE, not the content Claude decides to extract. It
# does NOT fix the earlier raw_query-paraphrasing tech debt (Claude
# rewording "secure lockers" down to just "secure") — that's a content
# behavior, unrelated to how the output gets serialized.
INTENT_TOOL = {
    "name": "extract_search_intent",
    "description": "Extract structured search intent from a traveler's natural language hostel search query.",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": ["string", "null"],
                "description": "City, region, or country name mentioned in the query, or null if not mentioned.",
            },
            "budget_max": {
                "type": ["number", "null"],
                "description": "Maximum price per night as a number, or null if not mentioned.",
            },
            "budget_flexibility": {
                "type": "string",
                "enum": ["strict", "approximate"],
            },
            "stay_duration_signal": {
                "type": "string",
                "enum": ["short_term", "long_term", "unknown"],
            },
            "party_preference": {
                "type": "string",
                "enum": ["avoid", "prefer_quiet", "neutral", "prefer_social", "prefer_party"],
            },
            "daytime_vibe_preference": {
                "enum": ["quiet", "social", None],
                "description": "Only non-null when the query clearly names a different vibe for daytime vs. evening — see the daytime/evening instructions above.",
            },
            "evening_vibe_preference": {
                "enum": ["quiet", "social", None],
                "description": "Only non-null when the query clearly names a different vibe for daytime vs. evening — see the daytime/evening instructions above.",
            },
            "vibe_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific vibe keywords extracted from the query.",
            },
            "traveler_profile": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Inferred traveler types based on context, per the inference rules above.",
            },
            "expand_search_requested": {
                "type": "boolean",
                "description": "True only when the query explicitly invites a wider geographic net around the named location — words like 'nearby', 'surrounding', 'around there', 'or close by', 'in the area'. False for a query that names just one specific place with no such language, even if that place turns out to be small.",
            },
        },
        "required": [
            "location", "budget_max", "budget_flexibility", "stay_duration_signal",
            "party_preference", "daytime_vibe_preference", "evening_vibe_preference",
            "vibe_tags", "traveler_profile", "expand_search_requested",
        ],
    },
}


# Prompt caching (added after a deliberate review of what was still missing
# from the AI-engineering checklist — see DECISIONS_LOG.md): this
# instructional block is IDENTICAL on every single call to parse_intent(),
# regardless of the traveler's actual query — only "Query: {query}" ever
# changes. Splitting it out of the per-request prompt into `system` (with
# a cache_control breakpoint) means Anthropic can cache this fixed prefix
# server-side and charge the much cheaper cache-read rate on every call
# after the first, instead of re-billing full input-token price for the
# same ~700 tokens of instructions on every search. Note honestly: caching
# only activates once a cacheable prefix crosses Anthropic's per-model
# minimum token threshold (1024 tokens for Sonnet) — this block plus the
# INTENT_TOOL schema that precedes it in the request should clear that,
# but it's not guaranteed for every model/version; the code is correct
# either way; it simply won't get a cache hit below the threshold.
INTENT_SYSTEM_PROMPT = """You are an expert travel analyst who understands deep traveler psychology.
Extract structured information from the traveler's hostel search query.

For traveler_profile, go beyond surface labels. Infer deeper traveler types based on context clues:
- Mentions metro/public transport access → likely "long_term_traveler", "daily_commuter"
- Mentions local market, cooking, fish bazaar, grocery shopping → likely "long_term_traveler", "self_cooker", "local_immersion_seeker"
- Mentions quiet after certain hour, early morning → "peace_lover", "early_riser"
- Mentions budget, cheap, under $X → "budget_conscious"
- Mentions wifi, work, laptop → "digital_nomad"
- Mentions party, nightlife, social → "party_traveler"
- Mentions culture, museum, history → "culture_seeker"
- Mentions hiking, trekking, adventure → "adventure_traveler"
- Short stay signals (1-2 nights, transit) → "transit_traveler"

For stay_duration_signal, combine weak signals rather than requiring an explicit mention:
- If 2 or more long-stay indicators are present together, set stay_duration_signal to "long_term"
- If explicit short stay language is used, set stay_duration_signal to "short_term"
- Only use "unknown" if there are truly no contextual clues either way

For budget_flexibility, distinguish two different kinds of budget language:
- "strict" — the traveler named a hard ceiling: "under $15", "no more than $10", "max $20", "below $8"
- "approximate" — the traveler named a rough target, not a hard cutoff: "around $10", "about $15", "roughly $20", "~$12"
- Default to "strict" if budget_max is null (no budget mentioned at all) or if the wording is ambiguous — approximate should only be used when the language clearly signals flexibility.

For party_preference, classify where the traveler sits on a party/social spectrum, even if not stated in those exact words. Pay attention to INTENSITY, not just direction:
- "avoid" — a strong, explicit rejection of party atmosphere: "not a party place", "no party scene", "definitely not a party hostel"
- "prefer_quiet" — a milder preference for lower-key over lively, without fully rejecting all social energy: "not much a party place", "priority is calmness", "somewhere chill", "low-key would be nice"
- "neutral" — no signal either way about party/social atmosphere
- "prefer_social" — wants a social, lively atmosphere without necessarily being a full-on party hostel: "sociable", "like meeting people", "good vibe in the evenings"
- "prefer_party" — explicitly wants a party hostel, nightlife, loud social scene: "party hostel", "nightlife", "want to rage"
- Default to "neutral" if there's no clear signal either way.
- ALWAYS fill this field the same way regardless of whether daytime_vibe_preference/evening_vibe_preference below are also set — it's the fallback the matching engine uses for any query that isn't genuinely time-varying.

For daytime_vibe_preference and evening_vibe_preference (EXPERIMENTAL, see DECISIONS_LOG.md — hostel-side day/night data doesn't exist yet, these are currently only exercised against a synthetic test fixture): only set these two fields — each "quiet", "social", or null — when the query CLEARLY expresses a DIFFERENT preference for daytime vs. evening within the same stay. This is a genuinely different signal than party_preference, which describes one overall vibe.
- Example that SHOULD set both: "somewhere I can focus during the day but still meet people over dinner" → daytime_vibe_preference: "quiet", evening_vibe_preference: "social".
- Example that SHOULD set both: "quiet mornings, social nights" → daytime_vibe_preference: "quiet", evening_vibe_preference: "social".
- Example that should NOT set either (leave both null): "chill hostel, not too party" — this is one overall preference, not a day/night split; party_preference alone covers it.
- Example that should NOT set either: "party hostel with nightlife" — also one overall preference.
- Default: leave BOTH null unless the query genuinely names two different times of day with two different vibes.

For expand_search_requested, set true ONLY when the query explicitly invites a wider net around the named location, not just because the place sounds small or remote:
- Set true: "Kathmandu or surrounding", "Lovina and nearby areas", "somewhere around Ubud", "close to Pai, doesn't have to be exact", "in the Amed area"
- Set false: "Kathmandu" alone, "a quiet hostel in Lovina", "Pai, budget backpacker energy" — these name one specific place with no widening language, even though the matching engine may still widen the search later on its own if too few results exist there. This field is only about what the TRAVELER explicitly asked for, not a prediction of whether their exact location will have enough options.
- Default to false whenever in doubt.

Call the extract_search_intent tool with the extracted fields."""


def parse_intent(query: str) -> dict:
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        system=[
            {
                "type": "text",
                "text": INTENT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[INTENT_TOOL],
        tool_choice={"type": "tool", "name": "extract_search_intent"},
        messages=[{"role": "user", "content": f'Query: "{query}"'}],
    )

    log_cache_usage("parse_intent", message.usage)
    return extract_tool_input(message, "extract_search_intent")


# Task #7 (DECISIONS_LOG.md): forced-tool-call schema for generate_explanation().
# Same reasoning as INTENT_TOOL above — the tone/style instructions (fragment
# style, severity-weighted flagged issues, "never pad heads_ups") stay in the
# prompt text; this only constrains output shape.
EXPLANATION_TOOL = {
    "name": "generate_hostel_explanation",
    "description": "Produce a short, scannable explanation of why a hostel matched a traveler's search.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "description": "One short, honest phrase (under 10 words) judging overall fit — can be lukewarm or mixed if that's accurate, never just positive spin for its own sake.",
            },
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
                "description": "1 to 4 short fragments, each a specific concrete reason this hostel fits — NOT full sentences.",
            },
            "heads_ups": {
                "type": "array",
                "items": {"type": "string"},
                "description": "0 or more short fragments for genuine caveats or flagged issues relevant to THIS search — empty list if there's nothing worth flagging, never pad to hit a count.",
            },
        },
        "required": ["verdict", "highlights", "heads_ups"],
    },
}


# Same prompt-caching reasoning as INTENT_SYSTEM_PROMPT above: this preamble
# (tone/persona + output-format rules) never changes between calls — only
# the per-hostel content in the user message does. Splitting it into
# `system` with a cache_control breakpoint lets it get cached the same way.
# Honest caveat: this particular block is short (well under the ~1024-token
# minimum Sonnet needs to actually cache), so on its own it likely won't hit
# a real cache read yet — it's still the architecturally correct place for
# it (static instructions belong in `system`, not re-sent inline every call)
# and the pattern is ready to benefit automatically if this preamble grows,
# or once combined with the EXPLANATION_TOOL schema that precedes it.
EXPLANATION_SYSTEM_PROMPT = """You are a fast, honest travel assistant. A backpacker is scanning search results
quickly — often on their phone, sometimes standing on a street with a bag on their back, not
sitting down to read a paragraph. Respond with SHORT, SCANNABLE fragments, not full sentences
joined into prose.

Each highlight and heads_up must be a short scannable fragment (roughly 5-12 words), written like
a label a tired person can read in half a second — not a grammatically complete sentence.

Call the generate_hostel_explanation tool with the result."""


def generate_explanation(intent: dict, hostel: dict, breakdown: list) -> dict:
    reasons_text = "\n".join(f"- {b['reason']}" for b in breakdown)

    flagged_issues = hostel.get("flagged_issues", [])
    flagged_text = ""
    if flagged_issues:
        flagged_lines = "\n".join(
            f"- {f['issue']} (frequency: {f.get('frequency', 'unknown')}, severity: {f.get('severity', 'unknown')})"
            for f in flagged_issues
        )
        flagged_text = f"""

Known flagged issues from past guest reviews:
{flagged_lines}

Include EVERY flagged issue that's genuinely relevant to this traveler's specific search — not
just one. If the traveler asked about safety and there's a safety-related flag, that's relevant;
a flagged issue about something the traveler didn't ask about (e.g. unrelated to their search)
can be left out. When multiple issues are included, order them most severe first. Weight tone by
SEVERITY, not just frequency — a "serious" issue must be treated with real weight regardless of
how rare it is; a "minor" issue can be phrased lightly."""

    prompt = f"""Traveler's search intent:
{json.dumps(intent, indent=2)}

Hostel: {hostel.get('name')} in {hostel.get('city')}, {hostel.get('country')}
Exclusive features: {', '.join(hostel.get('exclusive_features', [])) or 'none listed'}
Vibe tags: {', '.join(hostel.get('vibe_tags', [])) or 'none listed'}
Reviews summary: {hostel.get('reviews_summary', 'not available')}

Why the matching engine scored this hostel for this search:
{reasons_text}
{flagged_text}"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        system=[
            {
                "type": "text",
                "text": EXPLANATION_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[EXPLANATION_TOOL],
        tool_choice={"type": "tool", "name": "generate_hostel_explanation"},
        messages=[{"role": "user", "content": prompt}],
    )

    log_cache_usage("generate_explanation", message.usage)
    return extract_tool_input(message, "generate_hostel_explanation")


@app.post("/search")
@limiter.limit("10/minute")
def search(request: Request, body: SearchRequest):
    intent = parse_intent(body.query)
    outcome = match_hostels(
        intent, HOSTELS, top_n=10,
        raw_query=body.query,
        hostel_embeddings=HOSTEL_EMBEDDINGS,
    )

    return {
        "parsed_intent": intent,
        "total_matches": outcome["total_matches"],
        "results_returned": len(outcome["results"]),
        "results": outcome["results"],
    }


@app.post("/explain")
@limiter.limit("20/minute")
def explain(request: Request, body: ExplainRequest):
    hostel = HOSTELS_BY_ID.get(body.hostel_id)
    if hostel is None:
        raise HTTPException(status_code=404, detail="Hostel not found")

    breakdown = [{"points": b.points, "reason": b.reason} for b in body.breakdown]
    result = generate_explanation(body.intent, hostel, breakdown)

    # result is already {"verdict": ..., "highlights": [...], "heads_ups": [...]}
    return result
