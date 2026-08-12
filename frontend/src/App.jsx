import { useState } from 'react';

const SEARCH_URL = 'http://127.0.0.1:8000/search';
const EXPLAIN_URL = 'http://127.0.0.1:8000/explain';

function ScoreBreakdown({ breakdown }) {
  return (
    <ul style={{ marginTop: 8, paddingLeft: 20, fontSize: 14, color: '#444' }}>
      {breakdown.map((entry, i) => (
        <li key={i}>
          <strong style={{ color: entry.points >= 0 ? '#2a7a2a' : '#b33' }}>
            {entry.points >= 0 ? `+${entry.points}` : entry.points}
          </strong>
          {'  '}
          {entry.reason}
        </li>
      ))}
    </ul>
  );
}

function AiExplanation({ intent, hostelId, breakdown }) {
  // All local to THIS card — same reasoning as showBreakdown below.
  // Each card's AI explanation is fetched and shown independently.
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [visible, setVisible] = useState(false);

  async function handleClick() {
    // Already fetched once? Just toggle visibility, don't call the API again.
    if (explanation) {
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
      setExplanation(result.explanation);
      setVisible(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={handleClick}
        disabled={loading}
        style={{ fontSize: 13, padding: '4px 10px', cursor: 'pointer' }}
      >
        {loading ? 'Thinking...' : visible ? 'Hide AI explanation' : 'Get AI explanation'}
      </button>

      {error && <p style={{ color: '#b33', fontSize: 13, marginTop: 6 }}>Error: {error}</p>}

      {visible && explanation && (
        <p style={{ marginTop: 8, fontSize: 14, fontStyle: 'italic', color: '#333', lineHeight: 1.5 }}>
          {explanation}
        </p>
      )}
    </div>
  );
}

function HostelCard({ hostel, intent }) {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const price = hostel.price_range_usd;

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 style={{ margin: 0 }}>{hostel.name}</h3>
        <span style={{ fontSize: 14, color: '#666' }}>Score: {hostel.score}</span>
      </div>
      <p style={{ margin: '4px 0', color: '#666' }}>
        {hostel.city}, {hostel.country}
        {price && ` — $${price.min}${price.max && price.max !== price.min ? `-$${price.max}` : ''}/night`}
      </p>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={() => setShowBreakdown(!showBreakdown)}
          style={{ fontSize: 13, padding: '4px 10px', cursor: 'pointer' }}
        >
          {showBreakdown ? 'Hide scoring details' : 'Show scoring details'}
        </button>
      </div>

      {showBreakdown && <ScoreBreakdown breakdown={hostel.breakdown} />}

      <AiExplanation intent={intent} hostelId={hostel.id} breakdown={hostel.breakdown} />
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
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        placeholder="Describe your ideal hostel... (e.g. quiet hostel in Goa under $15)"
        style={{ flex: 1, padding: 10, fontSize: 16 }}
        disabled={loading}
      />
      <button
        onClick={handleSearch}
        disabled={loading}
        style={{ padding: '10px 20px', fontSize: 16, whiteSpace: 'nowrap' }}
      >
        {loading ? 'Searching...' : 'Search'}
      </button>
    </div>
  );
}

function Results({ loading, error, data }) {
  if (loading) return <p>Searching real hostels...</p>;
  if (error) return <p style={{ color: '#b33' }}>Error: {error}</p>;
  if (!data) return <p>Type a vibe above and hit Search.</p>;

  if (data.total_matches === 0) {
    return <p>No hostels matched that search. Try a different location or vibe.</p>;
  }

  return (
    <div>
      <p style={{ color: '#666', fontSize: 14 }}>
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
    <div style={{ padding: 30, maxWidth: 700, margin: '0 auto' }}>
      <h1>VibeMatch</h1>
      <p>Find your perfect hostel by vibe — now powered by real search.</p>
      <SearchBox onSearch={handleSearch} loading={loading} />
      <Results loading={loading} error={error} data={data} />
    </div>
  );
}

export default App;
