import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import SessionTimeoutModal from './SessionTimeoutModal';
import {
  isAnySessionActive,
  initSessionTimeout,
  extendSessionTimeout,
  performLogout,
  validateSessionOrPurge,
  SESSION_EXPIRES_KEY,
  WARNING_SECONDS,
  getJwtExpiryMs,
} from '../../../lib/sessionManager';

// Routes where a session warning should never be displayed
const AUTH_ROUTES = [
  '/login',
  '/signup',
  '/admin-login',
  '/forgot-password',
  '/verify-otp',
  '/reset-password',
];

/**
 * SessionTimeoutWatcher
 *
 * Runs globally within the app Router.
 * Monitors the 1-minute auto logout timer for logged-in users.
 * Displays the 10-second countdown popup when 10 seconds remain.
 * Automatically logs out and redirects when the timer reaches 0.
 * Also handles tab closure, visibility changes, and window focus so that
 * re-opening or switching to the tab after 1 minute triggers instant logout.
 */
const SessionTimeoutWatcher = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [showModal, setShowModal] = useState(false);
  const [countdown, setCountdown] = useState(WARNING_SECONDS);
  const isLoggingOutRef = useRef(false);

  const isAuthRoute = AUTH_ROUTES.includes(location.pathname);

  const handleLogout = useCallback((expired = false) => {
    if (isLoggingOutRef.current) return;
    isLoggingOutRef.current = true;
    setShowModal(false);
    performLogout({ expired, navigate });
    setTimeout(() => {
      isLoggingOutRef.current = false;
    }, 1000);
  }, [navigate]);

  const handleStayLoggedIn = useCallback(async () => {
    await extendSessionTimeout();
    setShowModal(false);
    setCountdown(WARNING_SECONDS);
  }, []);

  const handleLogoutNow = useCallback(() => {
    handleLogout(false);
  }, [handleLogout]);

  useEffect(() => {
    // Public auth routes don't run session timer checks
    if (isAuthRoute) {
      return undefined;
    }

    const checkSession = () => {
      if (isLoggingOutRef.current) return;

      const loggedIn = isAnySessionActive();
      if (!loggedIn) {
        setShowModal(false);
        return;
      }

      // Check both JWT expiry and local timer
      const token = localStorage.getItem('authToken') || localStorage.getItem('adminAuthToken');
      const jwtExp = getJwtExpiryMs(token);
      let rawExpires = localStorage.getItem(SESSION_EXPIRES_KEY);

      if (!rawExpires) {
        // Logged in without a session timestamp: initialize 1-minute timer now
        const newExpires = initSessionTimeout();
        rawExpires = String(newExpires);
      }

      let expiresAt = Number(rawExpires);
      if (jwtExp) {
        expiresAt = expiresAt ? Math.min(expiresAt, jwtExp) : jwtExp;
      }

      if (!expiresAt || Number.isNaN(expiresAt)) {
        initSessionTimeout();
        return;
      }

      const remainingMs = expiresAt - Date.now();
      const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000));

      if (remainingSec <= 0) {
        // 1-minute limit reached (even if user closed and reopened tab!)
        handleLogout(true);
      } else if (remainingSec <= WARNING_SECONDS) {
        // Display 10-second warning popup
        setShowModal(true);
        setCountdown(remainingSec);
      } else {
        // More than 10 seconds remaining
        setShowModal(false);
      }
    };

    // Immediate check on route navigation, tab focus, or mount
    checkSession();

    // Check every 500ms for responsive seconds countdown
    const interval = setInterval(checkSession, 500);

    const onStorage = () => checkSession();
    const onTimerUpdated = () => checkSession();
    const onTimerCleared = () => {
      setShowModal(false);
    };
    const onFocus = () => {
      validateSessionOrPurge({ navigate });
      checkSession();
    };
    const onVisibilityChange = () => {
      if (!document.hidden) {
        validateSessionOrPurge({ navigate });
        checkSession();
      }
    };

    window.addEventListener('storage', onStorage);
    window.addEventListener('session-timer-updated', onTimerUpdated);
    window.addEventListener('session-timer-cleared', onTimerCleared);
    window.addEventListener('user-profile-updated', onStorage);
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      clearInterval(interval);
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('session-timer-updated', onTimerUpdated);
      window.removeEventListener('session-timer-cleared', onTimerCleared);
      window.removeEventListener('user-profile-updated', onStorage);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [isAuthRoute, location.pathname, handleLogout, navigate]);

  return (
    <SessionTimeoutModal
      isOpen={showModal && !isAuthRoute}
      countdown={countdown}
      onStayLoggedIn={handleStayLoggedIn}
      onLogoutNow={handleLogoutNow}
    />
  );
};

export default SessionTimeoutWatcher;
