import { useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export default function Home() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResponse(null);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/api/retrieval/ask`,
        { query },
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      setResponse(res.data);
    } catch (err) {
      setError(err.response?.data?.message || 'Query execution failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '40px auto', padding: '0 20px' }}>
      <div className="glass-card" style={{ padding: '32px' }}>
        <h1 style={{ marginBottom: '8px' }}>RAG Query Playground</h1>
        <p style={{ color: '#94a3b8', marginBottom: '24px' }}>
          Test the retrieval pipeline and verify Plan Guard rate-limiting rules.
        </p>

        <form onSubmit={handleQuerySubmit}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question (e.g. 'Summarize Q3 financial reports')..."
              required
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid rgba(255,255,255,0.2)',
                background: 'rgba(15, 23, 42, 0.6)',
                color: '#fff',
                fontSize: '15px',
              }}
            />
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '12px 24px',
                background: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                cursor: loading ? 'wait' : 'pointer',
              }}
            >
              {loading ? 'Executing...' : 'Run Query'}
            </button>
          </div>
        </form>

        {response && (
          <div
            style={{
              marginTop: '20px',
              padding: '16px',
              background: 'rgba(34, 197, 94, 0.1)',
              border: '1px solid #22c55e',
              borderRadius: '8px',
            }}
          >
            <p style={{ color: '#4ade80', fontWeight: 'bold' }}>✅ Success</p>
            <p style={{ color: '#e2e8f0', marginTop: '4px' }}>{response.message}</p>
          </div>
        )}

        {error && (
          <div
            style={{
              marginTop: '20px',
              padding: '16px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid #ef4444',
              borderRadius: '8px',
            }}
          >
            <p style={{ color: '#f87171', fontWeight: 'bold' }}>⚠️ Limit Reached or Error</p>
            <p style={{ color: '#e2e8f0', marginTop: '4px' }}>{error}</p>
            <div style={{ marginTop: '12px' }}>
              <Link
                to="/pricing"
                style={{
                  color: '#3b82f6',
                  fontWeight: '600',
                  textDecoration: 'underline',
                }}
              >
                Go to Pricing & Upgrade to Standard →
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
