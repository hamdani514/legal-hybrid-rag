import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google';
import { apiFetch, setToken } from '../../../lib/api';

/**
 * Google sign-in, verified on the server.
 *
 * This used to be a mock: clicking it stored a made-up user in localStorage
 * with no check at all. Now:
 *   - GET /api/auth/google/config says whether the backend has a real
 *     GOOGLE_CLIENT_ID (one source of truth: the client id the backend verifies
 *     against is the one the button is rendered with).
 *   - If it does, Google's own button (@react-oauth/google) returns an ID token
 *     ("credential"), POST /api/auth/google verifies its signature, audience and
 *     expiry server-side and returns {token, user} like the password login.
 *   - If it does not, the button stays visible but says "Google sign-in is not
 *     configured" — no token is ever issued to an unverified user.
 * The credential exchange uses plain fetch: it carries no token of ours, and a
 * 401 here is a rejected Google credential, not an expired session.
 */
const GoogleAuthButton = ({ text = 'Continue with Google', onSuccess, className = '' }) => {
  const [config, setConfig] = useState(null); // null while loading
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    apiFetch('/api/auth/google/config')
      .then((res) => (res.ok ? res.json() : { enabled: false, client_id: '' }))
      .catch(() => ({ enabled: false, client_id: '' }))
      .then((cfg) => {
        if (!cancelled) setConfig(cfg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCredential = async (credentialResponse) => {
    const credential = credentialResponse?.credential;
    if (!credential) {
      setMessage('Google did not return a sign-in credential. Please try again.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const res = await fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(data.detail || 'Google sign-in failed.');
        return;
      }
      setToken(data.token);
      localStorage.setItem('currentUser', JSON.stringify(data.user));
      if (onSuccess) {
        onSuccess(data.user);
      } else {
        navigate('/welcome');
      }
    } catch (err) {
      console.error('Google sign-in error:', err);
      setMessage('Failed to communicate with the authentication server.');
    } finally {
      setLoading(false);
    }
  };

  const enabled = Boolean(config?.enabled && config?.client_id);

  if (enabled) {
    const googleText = /sign\s*up/i.test(text) ? 'signup_with' : 'continue_with';
    return (
      <div className={`w-full flex flex-col items-center gap-1 ${className}`}>
        <GoogleOAuthProvider clientId={config.client_id}>
          <GoogleLogin
            onSuccess={handleCredential}
            onError={() => setMessage('Google sign-in was cancelled or failed.')}
            text={googleText}
            shape="rectangular"
            logo_alignment="center"
            width="400"
          />
        </GoogleOAuthProvider>
        {(loading || message) && (
          <span className="text-[11px] font-body text-[#76849F] text-center mt-0.5">
            {loading ? 'Verifying your Google account…' : message}
          </span>
        )}
      </div>
    );
  }

  const handleUnavailable = (e) => {
    e.preventDefault();
    setMessage(config === null ? 'Checking Google sign-in…' : 'Google sign-in is not configured.');
  };

  return (
    <div className="w-full flex flex-col gap-1">
      <button
        type="button"
        onClick={handleUnavailable}
        aria-disabled="true"
        className={`w-full bg-white py-[14px] px-4 font-body font-medium text-sm leading-5 text-[#0D1C32] text-center flex items-center justify-center gap-3 opacity-70 cursor-not-allowed shadow-[0_1px_2px_rgba(0,0,0,0.04)] ${className}`}
        style={{ border: '1px solid rgba(197, 198, 205, 0.45)' }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" className="shrink-0" aria-hidden="true">
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.67l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.66l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
        <span className="tracking-[0.2px]">{text}</span>
      </button>
      {message && (
        <span className="text-[11px] font-body text-[#76849F] text-center mt-0.5">{message}</span>
      )}
    </div>
  );
};

export default GoogleAuthButton;
