import { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export default function Pricing() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({
    plan: 'free',
    dailyQueriesUsed: 0,
    dailyQueriesLimit: 10,
  });
  const [msg, setMsg] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get(`${API}/api/payments/status`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        setStatus(res.data);
      } catch (err) {
        // Not logged in or error — default to free
      }
    };
    fetchStatus();
  }, []);

  const handleSubscribe = async () => {
    setLoading(true);
    setMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/api/payments/create-checkout-session`,
        {},
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );

      window.location.href = res.data.url;
    } catch (err) {
      setMsg(err.response?.data?.message || 'Failed to start checkout.');
      setLoading(false);
    }
  };

  const isStandard = status.plan === 'standard';

  return (
    <div style={{ padding: '40px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ textAlign: 'center', marginBottom: '30px', color: '#f8fafc' }}>
        Choose Your Plan
      </h1>

      <div
        style={{
          display: 'flex',
          gap: '20px',
          justifyContent: 'center',
          flexWrap: 'wrap',
        }}
      >
        {/* Free Plan */}
        <div
          className="glass-card"
          style={{
            padding: '30px',
            width: '320px',
            textAlign: 'center',
            background: !isStandard ? 'rgba(30, 41, 59, 0.9)' : 'rgba(30, 41, 59, 0.4)',
            border: !isStandard ? '1px solid #3b82f6' : '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <h2>Free</h2>
          <p style={{ fontSize: '32px', fontWeight: 'bold', margin: '10px 0' }}>Rs 0</p>
          <p style={{ color: '#94a3b8' }}>Forever free</p>
          <ul style={{ textAlign: 'left', marginTop: '20px', lineHeight: '1.8', listStyle: 'none' }}>
            <li>✅ Basic search</li>
            <li>✅ View emails</li>
            <li>✅ {status.dailyQueriesLimit || 10} queries / day</li>
            <li style={{ color: '#64748b' }}>❌ AI summary</li>
          </ul>
          {!isStandard && (
            <p style={{ marginTop: '15px', fontSize: '13px', color: '#38bdf8' }}>
              Used today: {status.dailyQueriesUsed || 0}/{status.dailyQueriesLimit || 10}
            </p>
          )}
          <button
            disabled
            style={{
              width: '100%',
              padding: '12px',
              marginTop: '20px',
              background: '#334155',
              color: '#94a3b8',
              border: 'none',
              borderRadius: '8px',
              cursor: 'not-allowed',
            }}
          >
            {!isStandard ? 'Current Plan' : 'Free'}
          </button>
        </div>

        {/* Standard Plan */}
        <div
          className="glass-card"
          style={{
            padding: '30px',
            width: '320px',
            textAlign: 'center',
            background: isStandard ? 'rgba(22, 101, 52, 0.2)' : 'rgba(30, 41, 59, 0.9)',
            border: '2px solid #2563eb',
          }}
        >
          <h2>Standard</h2>
          <p style={{ fontSize: '32px', fontWeight: 'bold', margin: '10px 0' }}>Rs 2800</p>
          <p style={{ color: '#94a3b8' }}>per month</p>
          <ul style={{ textAlign: 'left', marginTop: '20px', lineHeight: '1.8', listStyle: 'none' }}>
            <li>✅ Unlimited queries</li>
            <li>✅ AI summary</li>
            <li>✅ Full email threads</li>
            <li>✅ Priority support</li>
          </ul>
          <button
            onClick={handleSubscribe}
            disabled={loading || isStandard}
            style={{
              width: '100%',
              padding: '12px',
              marginTop: '20px',
              background: isStandard ? '#16a34a' : '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: loading ? 'wait' : isStandard ? 'default' : 'pointer',
            }}
          >
            {loading ? 'Redirecting...' : isStandard ? 'Current Plan' : 'Subscribe Now'}
          </button>
        </div>
      </div>

      {msg && (
        <p style={{ textAlign: 'center', marginTop: '20px', color: '#ef4444' }}>{msg}</p>
      )}
    </div>
  );
}
