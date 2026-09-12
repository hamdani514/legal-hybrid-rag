import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Reusable Google Authentication Button
 * Strictly styled to match the Verdict AI Sovereign Editorial aesthetic.
 */
const GoogleAuthButton = ({
  text = 'Continue with Google',
  onSuccess,
  className = '',
}) => {
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState('');
  const navigate = useNavigate();

  const handleClick = (e) => {
    e.preventDefault();
    if (loading) return;

    setLoading(true);
    setNotification('Connecting to Google Sovereign Auth...');

    // Simulate Google OAuth flow in UI
    setTimeout(() => {
      setLoading(false);
      setNotification('');
      if (onSuccess) {
        onSuccess({ provider: 'google', email: 'user.editorial@gmail.com', name: 'Legal Counsel' });
      } else {
        // UI demonstration fallback
        const mockUser = {
          name: 'Counselor at Law',
          email: 'counselor@verdictai.com',
          role: 'user',
          avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=120&q=80',
        };
        localStorage.setItem('currentUser', JSON.stringify(mockUser));
        navigate('/welcome');
      }
    }, 1200);
  };

  return (
    <div className="w-full flex flex-col gap-1">
      <button
        type="button"
        onClick={handleClick}
        disabled={loading}
        className={`w-full bg-white py-[14px] px-4 font-body font-medium text-sm leading-5 text-[#0D1C32] text-center flex items-center justify-center gap-3 hover:bg-[#F3F4F6] active:scale-[0.99] transition-all disabled:opacity-60 disabled:cursor-not-allowed shadow-[0_1px_2px_rgba(0,0,0,0.04)] ${className}`}
        style={{ border: '1px solid rgba(197, 198, 205, 0.45)' }}
      >
        {loading ? (
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#44474D]">
            <span className="w-4 h-4 border-2 border-[#0D1C32] border-t-transparent rounded-full animate-spin"></span>
            Authenticating...
          </div>
        ) : (
          <>
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
          </>
        )}
      </button>
      {notification && (
        <span className="text-[11px] font-body text-[#76849F] text-center animate-pulse mt-0.5">
          {notification}
        </span>
      )}
    </div>
  );
};

export default GoogleAuthButton;
