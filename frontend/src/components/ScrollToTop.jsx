import { useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';

/**
 * Start every newly opened page at the top.
 *
 * A route change in a single-page app is not a page load, so the browser kept
 * the previous page's scroll position: leaving the home page half-way down
 * opened /about or /pricing half-way down too. Mounted once in App.jsx.
 *
 *   link, menu or redirect to another page   -> top of the new page, or the
 *                                               section named in its #hash
 *   link to the page already open            -> top of it (the logo on the
 *   (logo on the home page, a menu item on      home page acts like a reload)
 *   its own page)
 *   browser Back / Forward (POP)             -> left alone, so the browser
 *                                               returns you to where you were
 *   only ?search or #hash changed            -> left alone (filters, tabs and
 *                                               in-page anchors do not jump)
 *
 * React Router gives every navigation a new `key`, even one to the URL that
 * is already open, which is how a click on the current page's link is seen.
 */
const ScrollToTop = () => {
  const { pathname, search, hash, key } = useLocation();
  const navigationType = useNavigationType();
  const previous = useRef({ pathname, search, hash });

  useLayoutEffect(() => {
    const before = previous.current;
    previous.current = { pathname, search, hash };
    if (navigationType === 'POP') return undefined;

    const samePage = before.pathname === pathname;
    const sameUrl = samePage && before.search === search && before.hash === hash;
    // Same page, different search or hash: an in-page change, not a reload.
    if (samePage && !sameUrl) return undefined;

    if (hash) {
      // The section may render a frame later than the route itself.
      const id = decodeURIComponent(hash.slice(1));
      const frame = requestAnimationFrame(() => {
        const target = document.getElementById(id);
        if (target) target.scrollIntoView({ block: 'start' });
        else window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      });
      return () => cancelAnimationFrame(frame);
    }

    // A click on the page already open scrolls up smoothly, so the reader sees
    // where they went; a new page simply opens at its top.
    window.scrollTo({ top: 0, left: 0, behavior: sameUrl ? 'smooth' : 'instant' });
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return null;
};

export default ScrollToTop;
