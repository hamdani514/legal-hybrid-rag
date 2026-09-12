/**
 * Shared motion language for the user-facing site.
 *
 * Everything animates transform/opacity only, and every variant has a
 * reduced-motion twin so `prefers-reduced-motion: reduce` collapses the
 * choreography to a plain cross-fade instead of removing feedback entirely.
 */

// Cinematic easing curves — slow settle, no overshoot on text.
export const EASE_OUT_EXPO = [0.16, 1, 0.3, 1];
export const EASE_IN_OUT_EXPO = [0.87, 0, 0.13, 1];
export const EASE_OUT_SOFT = [0.22, 0.61, 0.36, 1];

export const DUR = {
  fast: 0.28,
  base: 0.55,
  slow: 0.9,
  film: 1.4,
};

/** Reveal on scroll — fires once, a quarter of the block in view. */
export const VIEWPORT = { once: true, amount: 0.25 };
export const VIEWPORT_SOFT = { once: true, amount: 0.12 };

export const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0, transition: { duration: DUR.base, ease: EASE_OUT_EXPO } },
};

export const fadeDown = {
  hidden: { opacity: 0, y: -20 },
  show: { opacity: 1, y: 0, transition: { duration: DUR.base, ease: EASE_OUT_EXPO } },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: DUR.slow, ease: EASE_OUT_SOFT } },
};

export const slideLeft = {
  hidden: { opacity: 0, x: -36 },
  show: { opacity: 1, x: 0, transition: { duration: DUR.base, ease: EASE_OUT_EXPO } },
};

export const slideRight = {
  hidden: { opacity: 0, x: 36 },
  show: { opacity: 1, x: 0, transition: { duration: DUR.base, ease: EASE_OUT_EXPO } },
};

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.94 },
  show: { opacity: 1, scale: 1, transition: { duration: DUR.slow, ease: EASE_OUT_EXPO } },
};

/** Slow push-in used behind banner artwork — the "camera" move. */
export const filmIn = {
  hidden: { opacity: 0, scale: 1.08 },
  show: { opacity: 1, scale: 1, transition: { duration: DUR.film, ease: EASE_OUT_EXPO } },
};

/** Gold hairline that draws itself out from the left. */
export const drawRule = {
  hidden: { scaleX: 0 },
  show: { scaleX: 1, transition: { duration: DUR.slow, ease: EASE_OUT_EXPO } },
};

/** Parent container: children inherit `hidden`/`show` and play in sequence. */
export const stagger = (staggerChildren = 0.09, delayChildren = 0) => ({
  hidden: {},
  show: { transition: { staggerChildren, delayChildren } },
});

/** Per-word headline reveal — the signature "title card" move. */
export const wordReveal = {
  hidden: { opacity: 0, y: '0.6em', rotateX: -55 },
  show: { opacity: 1, y: '0em', rotateX: 0, transition: { duration: 0.8, ease: EASE_OUT_EXPO } },
};

/** Route-level transition, driven by <AnimatePresence mode="wait">. */
export const pageVariants = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE_OUT_EXPO } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.3, ease: EASE_IN_OUT_EXPO } },
};

/** Flattened twins used whenever the OS asks for reduced motion. */
export const reducedVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.2 } },
};

export const reducedPageVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

/**
 * Pick the right variant set for the current motion preference.
 * `shouldReduce` comes from motion's `useReducedMotion()`.
 */
export const motionSafe = (variants, shouldReduce) => (shouldReduce ? reducedVariants : variants);

/** Hover lift shared by every card on the site. */
export const hoverLift = {
  rest: { y: 0 },
  hover: { y: -6, transition: { duration: DUR.fast, ease: EASE_OUT_EXPO } },
};
