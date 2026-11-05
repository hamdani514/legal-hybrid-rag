import { useSyncExternalStore } from 'react';

// Below Tailwind's `lg` breakpoint the workspace sidebar becomes a drawer over the
// page instead of a column beside it: a 288 px column leaves a phone almost no room.
const QUERY = '(max-width: 1023px)';

const subscribe = (onChange) => {
  const media = window.matchMedia(QUERY);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
};

const useIsMobile = () => useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => false);

export default useIsMobile;
