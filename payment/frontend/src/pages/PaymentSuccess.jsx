import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const [count, setCount] = useState(5);

  useEffect(() => {
    const timer = setInterval(() => {
      setCount((c) => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (count === 0) {
      navigate('/pricing', { replace: true });
    }
  }, [count, navigate]);

  return (
    <div style={{ padding: '60px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }} className="glass-card">
      <h1 style={{ color: '#22c55e', marginBottom: '16px' }}>✅ Payment Successful!</h1>
      <p style={{ fontSize: '18px', color: '#e2e8f0', marginBottom: '12px' }}>Your Standard plan is now active.</p>
      <p style={{ color: '#94a3b8' }}>
        Redirecting in {count} second{count !== 1 ? 's' : ''}...
      </p>
    </div>
  );
}
