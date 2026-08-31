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
        throw new Error(`Request failed with status ${response.status}`);
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

function Results({ loading, error, data }) {
  if (loading) return <p className="vm-status">Searching real hostels…</p>;
  if (error) return <p className="vm-status vm-error">Error: {error}</p>;
  if (!data) return <p className="vm-status">Type a vibe above and hit Search.</p>;

  if (data.total_matches === 0) {
    return <p className="vm-status">No hostels matched that search. Try a different location or vibe.</p>;
  }

  return (
    <div>
      <p className="vm-summary">
        {data.total_matches} total matches — showing top {data.results_returned}
      </p>
      {data.results.map((hostel) => (
        <HostelCard key={hostel.id} hostel={hostel} intent={data.parsed_intent} />
      ))}
    </div>
  );
}

function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  async function handleSearch(query) {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(SEARCH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="vm-app">
      <header className="vm-header">
        <h1 className="vm-title">VibeMatch</h1>
        <p className="vm-tagline">find your next stay, matched to your vibe</p>
      </header>

      <SearchBox onSearch={handleSearch} loading={loading} />
      <Results loading={loading} error={error} data={data} />
    </div>
  );
}

export default App;
