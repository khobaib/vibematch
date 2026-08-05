import { useState } from "react";

const hostels = [
  { id: 1, name: 'Mad Monkey', city: 'Bangkok', price: 12, tags: ['social', 'party', 'rooftop'] },
  { id: 2, name: 'Tribal Hostel', city: 'Goa', price: 8, tags: ['beach', 'chill', 'social'] },
  { id: 3, name: 'Zostel', city: 'Manali', price: 10, tags: ['mountain', 'adventure', 'quiet'] },
  { id: 4, name: 'Bodhi Hostel', city: 'Kathmandu', price: 5, tags: ['rooftop', 'budget', 'view'] },
  { id: 5, name: 'Submarine', city: 'Bali', price: 15, tags: ['beach', 'pool', 'social'] },
  { id: 6, name: 'The Hive', city: 'Lisbon', price: 18, tags: ['social', 'workcation', 'wifi'] },
  { id: 7, name: 'Dreamcatcher', city: 'Medellín', price: 14, tags: ['social', 'rooftop', 'party'] },
  { id: 8, name: 'Jungle House', city: 'Chiang Mai', price: 9, tags: ['nature', 'quiet', 'adventure'] },
  { id: 9, name: 'Cox Nomad', city: 'Dhaka', price: 5, tags: ['cheap', 'local', 'beach'] },
];

function searchHostels(query) {
  if (!query.trim()) {
    return [];
  }

  const keywords = query.toLowerCase().split(' ');
  return hostels.filter(hostel => 
    keywords.every(keyword => hostel.tags.some(tag => tag.includes(keyword)))
  );
}

function HostelCard({ hostel }) {
  return (
    <div style={{ border: '1px solid #ccc', padding: 15, marginBottom: 10, borderRadius: 8 }}>
      <h3>{hostel.name}</h3>
      <p>{hostel.city}</p>
      <p>${hostel.price} per night</p>
      <div>
        {hostel.tags.map((tag) => (
          <span
            key={tag}
            style={{
              background: '#e0f0ff',
              padding: '2px 8px',
              borderRadius: 12,
              marginRight: 6,
              fontSize: 12,
            }}
          >
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

function SearchBox({ onSearch, onClear, query }) {
  const [localQuery, setLocalQuery] = useState('');

  function handleSearch() {
    onSearch(localQuery.trim());  // updates App's query state → shows results
  };

  function handleClear() {
    setLocalQuery('');    // clears the input box
    onClear();            // clears App's query state → hides results
  }

  return (
    <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10}}>
      <input
        value={localQuery}
        onChange={(e) => setLocalQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        placeholder="Describe your ideal hostel... (e.g. beach social)"
        style={{ flex: 1, padding: 10, fontSize: 16 }}
      />
      <button
        onClick={handleSearch}
        style={{ padding: '10px 20px', whiteSpace: 'nowrap', fontSize: 16 }}
      >
        Search
      </button>
      {query.length > 0 && (
      <button
        onClick={handleClear}
        style={{ padding: '10px 20px', whiteSpace: 'nowrap', fontSize: 16 }}
      >
        Clear
      </button>
      )}
    </div>
  );
}

function Results({ query }) {
  if (!query) {
    return <p>Type a vibe above and hit Search.</p>;
  }

  const results = searchHostels(query);

  if (results.length === 0) {
    return <p>No hostels found for "{query}". Try "beach", "social", or "mountain".</p>;
  }

  return (
    <div>
      <p>{results.length} hostel(s) found for "{query}"</p>
      {results.map((hostel) => (
        <HostelCard key={hostel.id} hostel={hostel} />
      ))}
    </div>
  );
}


function App() {
  const [query, setQuery] = useState('');
 
  return (
    <div style={{ padding: 30, maxWidth: 700, margin: '0 auto' }}>
      <h1>VibeMatch</h1>
      <p>Find your perfect hostel by vibe.</p>
      <SearchBox onSearch={setQuery} onClear={() => setQuery('')} query={query} />
      <Results query={query} />
    </div>
  );
}

export default App;