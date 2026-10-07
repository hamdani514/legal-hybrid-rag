import { Link } from 'react-router-dom';

export default function PaymentCancel() {
  return (
    <div style={{ padding: '60px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }} className="glass-card">
      <h1 style={{ color: '#ef4444', marginBottom: '16px' }}>❌ Payment Cancelled</h1>
      <p style={{ fontSize: '18px', color: '#e2e8f0', marginBottom: '24px' }}>No charges were made.</p>
      <Link to="/pricing" style={{ color: '#3b82f6', textDecoration: 'underline' }}>
        ← Back to pricing
      </Link>
    </div>
  );
}
