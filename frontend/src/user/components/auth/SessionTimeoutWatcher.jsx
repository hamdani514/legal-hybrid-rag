import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import SessionTimeoutModal from './SessionTimeoutModal';
import {
  extendSessionTimeout,
  getSessionRemainingSeconds,
  performLogout,
  refreshSessionIfNeeded,
  validateSessionOrPurge,
  WARNING_SECONDS,
} from '../../../lib/sessionManager';

// How often the session is offered a silent renewal while the app is open.
const RENEW_CHECK_MS = 60 * 1000;

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
 * Runs globally within the app Router. Keeps the signed-in session alive: it
 * offers the session a silent renewal every minute and whenever the tab
 * regains focus (sessionManager renews a token once half its lifetime has
 * passed), so a user who has the app open is never sent back to the login page.
 *
 * Only a session that could not renew (the server unreachable for a long time,
 * or the token already expired while the app was closed) reaches its end: the
 * popup counts down the last WARNING_SECONDS with a "Stay signed in" button,
 * and at zero the session signs out to its login page.
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

      // The session of this page (user pages: the user's; /admin: the admin's).
      const remainingSec = getSessionRemainingSeconds();
      if (remainingSec === null) {
        setShowModal(false);
        return;
      }

      if (remainingSec <= 0) {
        handleLogout(true);
      } else if (remainingSec <= WARNING_SECONDS) {
        // Renewal has not succeeded in time: count down the last minute.
        refreshSessionIfNeeded();
        setShowModal(true);
        setCountdown(remainingSec);
      } else {
        setShowModal(false);
      }
    };

    // Immediate check on route navigation, tab focus, or mount
    refreshSessionIfNeeded();
    checkSession();

    // A cheap local check twice a second (the countdown needs it), and a
    // renewal offer every minute.
    const interval = setInterval(checkSession, 500);
    const renewer = setInterval(refreshSessionIfNeeded, RENEW_CHECK_MS);

    const onStorage = () => checkSession();
    const onTimerUpdated = () => checkSession();
    const onTimerCleared = () => {
      setShowModal(false);
    };
    const onFocus = () => {
      validateSessionOrPurge({ navigate });
      refreshSessionIfNeeded();
      checkSession();
    };
    const onVisibilityChange = () => {
      if (!document.hidden) {
        validateSessionOrPurge({ navigate });
        refreshSessionIfNeeded();
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
      clearInterval(renewer);
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
