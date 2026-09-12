import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { EASE_IN_OUT_EXPO } from '../../motion';

/**
 * Route change choreography.
 *
 * A wrapper that animates the whole page would create a containing block and
 * break every `position: fixed` element on the site (masthead, sidebar, chat
 * bar). So the transition is an overlay instead: an ink curtain wipes down
 * over the viewport and straight back off, leaving each page's own entrance
 * animation to play underneath.
 *
 * The curtain carries no state — keying it on the pathname remounts the node
 * on every navigation, which replays the keyframes.
 *
 * It also restores scroll position: top on a new route, or the anchored
 * element when the URL carries a hash.
 */
const RouteTransition = () => {
  const location = useLocation();
  const shouldReduce = useReducedMotion();

  // Scroll handling runs on every navigation, reduced motion included.
  useEffect(() => {
    if (location.hash) {
      const target = document.querySelector(location.hash);
      if (target) {
        target.scrollIntoView({ behavior: shouldReduce ? 'auto' : 'smooth', block: 'start' });
        return;
      }
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [location.pathname, location.hash, shouldReduce]);

  // The curtain is pure decoration.
  if (shouldReduce) return null;

  return (
    <motion.div
      key={location.pathname}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[100] surface-linen"
      initial={{ scaleY: 0, originY: 0 }}
      animate={{ scaleY: [0, 1, 1, 0], originY: [0, 0, 1, 1] }}
      transition={{ duration: 0.85, times: [0, 0.42, 0.5, 1], ease: EASE_IN_OUT_EXPO }}
    >
      <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-px rule-gold" />
    </motion.div>
  );
};

export default RouteTransition;
