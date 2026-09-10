import { useState } from 'react';
import './App.css';

// Task #10 (DECISIONS_LOG.md): API base URL now comes from a Vite env var
// instead of being hardcoded to localhost, so the same build works against
// the local dev backend and the deployed Fly.io backend. Vite only exposes
// env vars prefixed VITE_ to client code (a deliberate security boundary -
// anything without that prefix stays server/build-side only). Falls back to
// the original localhost URL when the env var isn't set, so `npm run dev`
// keeps working with zero extra setup. Set VITE_API_BASE_URL in a
// frontend/.env.production file (or in Vercel's project env var settings)
// once the real Fly.io URL is known, e.g. https://vibematch-backend.fly.dev.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const SEARCH_URL = `${API_BASE_URL}/search`;
const EXPLAIN_URL = `${API_BASE_URL}/explain`;

// The backend rate-limits /search and /explain per IP (see backend/main.py,
// DECISIONS_LOG.md) to protect against runaway LLM API costs. A throttled
// request comes back as HTTP 429 - without this, the UI just showed
// "Request failed with status 429", which is technically correct but means
// nothing to someone who isn't a developer. This turns that one case into a
// message an actual user can act on, while leaving every other error status
// to fall back to the original generic message.
function friendlyErrorMessage(status) {
  if (status === 429) {
    return "You're searching a bit fast — please wait a moment and try again.";
  }
  return `Request failed with status ${status}`;
}

function ScoreBreakdown({ breakdown }) {
  return (
    <ul className="vm-breakdown">
      {breakdown.map((entry, i) => (
        <li key={i}>
          <span className={entry.points >= 0 ? 'vm-points-positive' : 'vm-points-negative'}>
            {entry.points >= 0 ? `+${entry.points}` : entry.points}
          </span>
          {'  '}
          {entry.reason}
        </li>
      ))}
    </ul>
  );
}

function AiExplanation({ intent, hostelId, breakdown }) {
  const [data, setData] = useState(null); // { verdict, highlights, heads_ups }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [visible, setVisible] = useState(false);

  async function handleClick() {
    if (data) {
      setVisible(!visible);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(EXPLAIN_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent, hostel_id: hostelId, breakdown }),
      });

      if (!response.ok) {
        throw new Error(friendlyErrorMessage(response.status));
      }

      const result = await response.json();
      setData(result);
      setVisible(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button onClick={handleClick} disabled={loading} className="vm-btn-ghost">
        {loading ? 'Thinking…' : visible ? 'Hide AI note' : 'Get AI note'}
      </button>

      {error && <p className="vm-ai-error">Error: {error}</p>}

      {visible && data && (
        <div className="vm-ai-explanation">
          <p className="vm-ai-verdict">{data.verdict}</p>

          {data.highlights?.length > 0 && (
            <ul className="vm-ai-list">
              {data.highlights.map((h, i) => (
                <li key={i} className="vm-ai-highlight">{h}</li>
              ))}
            </ul>
          )}

          {data.heads_ups?.length > 0 && (
            <ul className="vm-ai-list">
              {data.heads_ups.map((h, i) => (
                <li key={i} className="vm-ai-headsup">{h}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}

function HostelCard({ hostel, intent }) {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const price = hostel.price_range_usd;

  return (
    <div className="vm-card">
      <div className="vm-card-main">
        <h3 className="vm-card-name">{hostel.name}</h3>
        <p className="vm-card-location">
          {hostel.city}, {hostel.country}
          {price && (
            <>
              {' — '}
              <span className="vm-card-price">
                ${price.min}{price.max && price.max !== price.min ? `–$${price.max}` : ''}/night
              </span>
            </>
          )}
        </p>

        <div className="vm-card-actions">
          <button onClick={() => setShowBreakdown(!showBreakdown)} className="vm-btn-ghost">
            {showBreakdown ? 'Hide scoring' : 'Show scoring'}
          </button>
          <AiExplanation intent={intent} hostelId={hostel.id} breakdown={hostel.breakdown} />
        </div>

        {showBreakdown && <ScoreBreakdown breakdown={hostel.breakdown} />}
      </div>

      <div className="vm-card-stub">
        <div className="vm-stamp">
          <span className="vm-stamp-score">{hostel.score}</span>
          <span className="vm-stamp-label">match</span>
        </div>
      </div>
    </div>
  );
}

// Client-side pagination page size. Pagination happens entirely in the
// browser against the full ranked list /search already returns — a page
// turn is just re-slicing an array already in memory, not another network
// call. This keeps it free of the rate limit (10/min, real LLM cost per
// call) that governs the actual /search and /explain endpoints.
const RESULTS_PER_PAGE = 10;

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;

  return (
    <div className="vm-pagination">
      <button
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="vm-btn-ghost"
      >
        ← Prev
      </button>
      <span className="vm-pagination-label">
        Page {page} of {totalPages}
      </span>
      <button
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="vm-btn-ghost"
      >
        Next →
      </button>
    </div>
  );
}

function SearchBox({ onSearch, loading }) {
  const [query, setQuery] = useState('');

  function handleSearch() {
    const trimmed = query.trim();
    if (trimmed) onSearch(trimmed);
  }

  return (
    <div className="vm-search">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        placeholder="Describe your ideal hostel… quiet hostel in Goa under $15"
        className="vm-input"
        disabled={loading}
      />
      <button onClick={handleSearch} disabled={loading} className="vm-search-btn">
        {loading ? 'Searching…' : 'Search'}
      </button>
    </div>
  );
}

function Results({ loading, error, data, page, onPageChange, onExpandSearch, expanding }) {
  if (loading) return <p className="vm-status">Searching real hostels…</p>;
  if (error) return <p className="vm-status vm-error">Error: {error}</p>;
  if (!data) return <p className="vm-status">Type a vibe above and hit Search.</p>;

  if (data.total_matches === 0 && !data.expansion_available) {
    return <p className="vm-status">No hostels matched that search. Try a different location or vibe.</p>;
  }

  const totalResults = data.results.length;
  const totalPages = Math.max(1, Math.ceil(totalResults / RESULTS_PER_PAGE));
  const pageResults = data.results.slice((page - 1) * RESULTS_PER_PAGE, page * RESULTS_PER_PAGE);

  return (
    <div>
      {/* Explicit-wording case ("Kathmandu or surrounding") — the traveler
          asked for a wider net directly, so say so plainly rather than
          leaving them to notice individual "expanded_search" tags. */}
      {data.expansion_message && (
        <p className="vm-expansion-banner">{data.expansion_message}</p>
      )}

      <p className="vm-summary">
        {data.total_matches} total matches — showing {pageResults.length ? `${(page - 1) * RESULTS_PER_PAGE + 1}-${(page - 1) * RESULTS_PER_PAGE + pageResults.length}` : '0'} of {totalResults}
      </p>

      {pageResults.map((hostel) => (
        <HostelCard key={hostel.id} hostel={hostel} intent={data.parsed_intent} />
      ))}

      <Pagination page={page} totalPages={totalPages} onPageChange={onPageChange} />

      {/* Thin-results case — nobody asked for a wider net, so nothing was
          silently added. Offer it as an explicit choice instead. Placed at
          the END of the list deliberately (UX decision, see
          DECISIONS_LOG.md): a traveler only wants this offer once they've
          actually seen what's here and decided it's not enough — putting it
          above the list means asking before they've even looked. */}
      {data.expansion_available && (
        <div className="vm-expansion-offer">
          <p>Not enough listings here — want to expand your search to nearby areas?</p>
          <button onClick={onExpandSearch} disabled={expanding} className="vm-btn-ghost">
            {expanding ? 'Expanding…' : 'Expand my search'}
          </button>
        </div>
      )}
    </div>
  );
}

function App() {
  const [loading, setLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  // Kept so "Expand my search" can re-send the same original query text —
  // the backend is stateless per-request, so widening the search means
  // calling /search again with the same query plus expand: true, not
  // continuing some server-side session.
  const [lastQuery, setLastQuery] = useState(null);

  async function runSearch(query, { expand = false } = {}) {
    try {
      const response = await fetch(SEARCH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, expand }),
      });

      if (!response.ok) {
        throw new Error(friendlyErrorMessage(response.status));
      }

      return await response.json();
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    setPage(1);
    setLastQuery(query);

    const result = await runSearch(query);
    if (result) setData(result);
    setLoading(false);
  }

  async function handleExpandSearch() {
    if (!lastQuery) return;
    setExpanding(true);
    setError(null);

    const result = await runSearch(lastQuery, { expand: true });
    if (result) {
      setData(result);
      setPage(1);
    }
    setExpanding(false);
  }

  return (
    <div className="vm-app">
      <header className="vm-header">
        <h1 className="vm-title">VibeMatch</h1>
        <p className="vm-tagline">find your next stay, matched to your vibe</p>
      </header>

      <SearchBox onSearch={handleSearch} loading={loading} />
      <Results
        loading={loading}
        error={error}
        data={data}
        page={page}
        onPageChange={setPage}
        onExpandSearch={handleExpandSearch}
        expanding={expanding}
      />
    </div>
  );
}

export default App;
