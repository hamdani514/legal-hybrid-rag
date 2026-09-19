import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';

export default function ReactivateAccountPage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('loading'); // 'loading' | 'success' | 'error'
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token || token.length < 32) {
      setStatus('error');
      setMessage('Invalid reactivation link. Please check your email for the correct link.');
      return;
    }

    const reactivate = async () => {
      try {
        const res = await fetch(`/api/auth/reactivate/${encodeURIComponent(token)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });

        const data = await res.json();
        if (res.ok) {
          setStatus('success');
          setMessage(data.message || 'Account successfully reactivated.');
          setTimeout(() => {
            navigate('/login');
          }, 3000);
        } else {
          setStatus('error');
          setMessage(data.detail || data.message || 'Reactivation failed. The link may have expired or already been used.');
        }
      } catch (err) {
        console.error('Reactivation error:', err);
        setStatus('error');
        setMessage('Unable to communicate with the server. Please check your connection.');
      }
    };

    reactivate();
  }, [token, navigate]);

  return (
    <AuthShell>
      <div className="pop-in flex w-full flex-col text-center">
        {/* State: Loading */}
        {status === 'loading' && (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="w-12 h-12 border-3 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
            <h1 className="font-display font-bold text-2xl text-ash-900">
              Reactivating Account...
            </h1>
            <p className="font-prose text-sm text-ash-600 max-w-sm">
              Verifying your cryptographic security token and restoring your account permissions.
            </p>
          </div>
        )}

        {/* State: Success */}
        {status === 'success' && (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mb-2">
              <span className="material-symbols-outlined text-3xl">check_circle</span>
            </div>
            <h1 className="font-display font-bold text-2xl text-ash-900">
              Account Reactivated!
            </h1>
            <p className="font-prose text-sm text-ash-600 max-w-sm">
              {message}
            </p>
            <div className="w-full bg-emerald-50 text-emerald-800 p-4 rounded-xl border border-emerald-200 text-xs font-prose flex items-center justify-center gap-2 mt-2">
              <span className="material-symbols-outlined text-sm">schedule</span>
              <span>Redirecting you to the Login portal in 3 seconds...</span>
            </div>
            <Link
              to="/login"
              className="grad-btn w-full rounded-full py-3.5 font-ui text-[14px] font-bold text-white shadow-glow transition-all duration-300 hover:shadow-glow-lg mt-4"
            >
              Sign In Now
            </Link>
          </div>
        )}

        {/* State: Error */}
        {status === 'error' && (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="w-14 h-14 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mb-2">
              <span className="material-symbols-outlined text-3xl">error</span>
            </div>
            <h1 className="font-display font-bold text-2xl text-ash-900">
              Reactivation Failed
            </h1>
            <p className="font-prose text-sm text-ash-600 max-w-sm">
              {message}
            </p>
            <div className="w-full bg-rose-50 text-rose-800 p-4 rounded-xl border border-rose-200 text-xs font-prose flex items-center justify-center gap-2 mt-2">
              <span className="material-symbols-outlined text-sm">info</span>
              <span>Reactivation links expire after 30 days or once successfully redeemed.</span>
            </div>
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-ash-200 bg-white px-6 py-3 font-ui text-[14px] font-semibold text-ash-900 transition-all duration-300 hover:border-brand-300 hover:text-brand-700 mt-4"
            >
              <span className="material-symbols-outlined text-sm">arrow_back</span>
              Return to Login
            </Link>
          </div>
        )}
      </div>
    </AuthShell>
  );
}
