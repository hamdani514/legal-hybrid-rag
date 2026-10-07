import { Link } from 'react-router-dom';

export default function Navbar() {
  return (
    <nav
      style={{
        display: 'flex',
        justify: 'space-between',
        alignItems: 'center',
        padding: '18px 40px',
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(10px)',
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}
    >
      <Link to="/" style={{ fontSize: '20px', fontWeight: 'bold', color: '#f8fafc' }}>
        ⚡ RAG Payment Module
      </Link>
      <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
        <Link to="/" style={{ color: '#94a3b8', fontWeight: '500' }}>
          Home
        </Link>
        <Link
          to="/pricing"
          style={{
            color: '#f8fafc',
            fontWeight: '600',
            background: 'rgba(59, 130, 246, 0.2)',
            padding: '8px 16px',
            borderRadius: '8px',
            border: '1px solid rgba(59, 130, 246, 0.4)',
          }}
        >
          Pricing
        </Link>
      </div>
    </nav>
  );
}
