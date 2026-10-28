import { useState, useEffect } from 'react';
import { isUserLoggedIn, validateSessionOrPurge } from '../../lib/sessionManager';

/**
 * React hook to reactively check if a user is currently logged in.
 * Automatically synchronizes on storage events and custom auth events.
 */
export function useIsLoggedIn() {
  const [loggedIn, setLoggedIn] = useState(() => {
    try {
      if (!validateSessionOrPurge()) return false;
      return isUserLoggedIn();
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const handleAuthChange = () => {
      try {
        if (!validateSessionOrPurge()) {
          setLoggedIn(false);
          return;
        }
        setLoggedIn(isUserLoggedIn());
      } catch {
        setLoggedIn(false);
      }
    };

    window.addEventListener('storage', handleAuthChange);
    window.addEventListener('user-profile-updated', handleAuthChange);
    return () => {
      window.removeEventListener('storage', handleAuthChange);
      window.removeEventListener('user-profile-updated', handleAuthChange);
    };
  }, []);

  return loggedIn;
}

export default useIsLoggedIn;
