import React from 'react';
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react';
import { EASE_OUT_EXPO } from '../../motion';

/**
 * Atmosphere primitives for the light "chambers" theme.
 *
 * Every layer here is decorative and `aria-hidden`. They are deliberately
 * faint: on a parchment ground, texture behind body copy costs readability
 * far faster than it buys depth, so these are used on banner and footer
 * bands rather than under running text.
 */

/** Laid-paper grain. Dark specks multiplied into the light ground. */
export const PaperGrain = ({ opacity = 0.35, className = '' }) => (
  <div
    aria-hidden="true"
    className={`pointer-events-none absolute inset-0 paper-grain ${className}`}
    style={{ opacity }}
  />
);

/** Soft warm falloff at the edges of a banner — the light-theme vignette. */
export const Vignette = ({ strength = 0.35, className = '' }) => (
  <div
    aria-hidden="true"
    className={`pointer-events-none absolute inset-0 ${className}`}
    style={{
      background: `radial-gradient(115% 85% at 50% 38%, rgba(242,236,223,0) 45%, rgba(230,221,201,${strength}) 100%)`,
    }}
  />
);

/** Slow warm light sweeping across a banner, like sun moving through a hall. */
export const LightSweep = ({ className = '', duration = 11 }) => {
  const shouldReduce = useReducedMotion();
  if (shouldReduce) return null;

  return (
    <motion.div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-y-0 -left-1/3 w-1/2 ${className}`}
      style={{
        background:
          'linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.55) 45%, rgba(255,255,255,0) 100%)',
      }}
      animate={{ x: ['0%', '460%'] }}
      transition={{ duration, ease: 'linear', repeat: Infinity, repeatDelay: 4 }}
    />
  );
};

/** Two drifting warm auras that keep large parchment areas from going flat. */
export const AuraField = ({ className = '' }) => {
  const shouldReduce = useReducedMotion();
  const drift = shouldReduce
    ? {}
    : { animate: { x: [0, 26, 0], y: [0, -18, 0], scale: [1, 1.08, 1] } };

  return (
    <div aria-hidden="true" className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <motion.span
        className="absolute -top-24 right-[-10%] h-[26rem] w-[26rem] rounded-full bg-gold-200/40 blur-[120px]"
        {...drift}
        transition={{ duration: 16, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.span
        className="absolute -bottom-32 left-[-8%] h-[30rem] w-[30rem] rounded-full bg-ink-100/50 blur-[140px]"
        {...(shouldReduce ? {} : { animate: { x: [0, -22, 0], y: [0, 20, 0] } })}
        transition={{ duration: 20, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  );
};

/** Courthouse colonnade in pale stone, parallaxing against the page scroll. */
export const ColonnadeLayer = ({ className = '', opacity = 0.5, distance = 60 }) => {
  const ref = React.useRef(null);
  const shouldReduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, distance]);

  return (
    <div ref={ref} aria-hidden="true" className={`pointer-events-none absolute inset-x-0 bottom-0 ${className}`}>
      <motion.img
        src="/assets/legal/colonnade.svg"
        alt=""
        loading="lazy"
        className="w-full select-none object-cover object-bottom"
        style={{ opacity, y: shouldReduce ? 0 : y }}
      />
    </div>
  );
};

/** Ruled "statute paper" texture, tiled. Decorative bands only. */
export const StatuteTexture = ({ className = '', opacity = 0.5 }) => (
  <div
    aria-hidden="true"
    className={`pointer-events-none absolute inset-0 ${className}`}
    style={{
      opacity,
      backgroundImage: 'url(/assets/legal/statute-pattern.svg)',
      backgroundSize: '120px 120px',
    }}
  />
);

/** Gold hairline that draws out when it enters the viewport. */
export const GoldRule = ({ className = '', width = 'w-24', delay = 0 }) => (
  <motion.span
    aria-hidden="true"
    className={`block h-px origin-left bg-gradient-to-r from-gold-600 via-gold-500 to-transparent ${width} ${className}`}
    initial={{ scaleX: 0, opacity: 0 }}
    whileInView={{ scaleX: 1, opacity: 1 }}
    viewport={{ once: true }}
    transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay }}
  />
);

/** Thin gold reading-progress bar pinned to the top of the viewport. */
export const ScrollProgress = () => {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 120, damping: 30, restDelta: 0.001 });

  return (
    <motion.div
      aria-hidden="true"
      className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left bg-gradient-to-r from-gold-600 via-gold-400 to-gold-600"
      style={{ scaleX }}
    />
  );
};

/** Wraps children in a scroll-linked vertical parallax. */
export const Parallax = ({ children, distance = 50, className = '' }) => {
  const ref = React.useRef(null);
  const shouldReduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [distance, -distance]);

  return (
    <div ref={ref} className={className}>
      <motion.div style={{ y: shouldReduce ? 0 : y }}>{children}</motion.div>
    </div>
  );
};
