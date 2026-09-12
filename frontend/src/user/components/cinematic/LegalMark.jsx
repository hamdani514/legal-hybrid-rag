import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { EASE_OUT_EXPO } from '../../motion';

/**
 * Inline legal iconography. These are drawn (not filled) so the strokes can
 * animate themselves on, which is what gives the banners their "etched" feel.
 * Every mark is decorative unless a `title` is supplied.
 */

// Plain helper, not a hook — the component reads the motion preference once
// and passes it in, so a mark can build a dozen stroke animations freely.
const draw = (shouldReduce, delay = 0, duration = 1.6) =>
  shouldReduce
    ? { initial: { opacity: 1, pathLength: 1 }, animate: { opacity: 1, pathLength: 1 } }
    : {
        initial: { pathLength: 0, opacity: 0 },
        animate: { pathLength: 1, opacity: 1 },
        transition: {
          pathLength: { duration, ease: EASE_OUT_EXPO, delay },
          opacity: { duration: 0.3, delay },
        },
      };

const svgProps = (title, className, size) => ({
  viewBox: '0 0 200 200',
  className,
  width: size,
  height: size,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 3,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  role: title ? 'img' : 'presentation',
  'aria-label': title || undefined,
  'aria-hidden': title ? undefined : 'true',
});

/** Scales of justice — the primary brand mark. */
export const ScalesMark = ({ className = '', size = 64, title, delay = 0 }) => {
  const r = useReducedMotion();
  return (
    <svg {...svgProps(title, className, size)}>
      <motion.path d="M100 26v138" {...draw(r, delay)} />
      <motion.circle cx="100" cy="20" r="7" fill="currentColor" stroke="none" {...draw(r, delay + 0.2, 0.4)} />
      <motion.path d="M30 52h140" {...draw(r, delay + 0.15)} />
      <motion.path d="M30 52 8 106h44z" {...draw(r, delay + 0.35)} />
      <motion.path d="M170 52l22 54h-44z" {...draw(r, delay + 0.35)} />
      <motion.path d="M8 106a22 22 0 0 0 44 0" {...draw(r, delay + 0.5)} />
      <motion.path d="M148 106a22 22 0 0 0 44 0" {...draw(r, delay + 0.5)} />
      <motion.path d="M70 164h60" {...draw(r, delay + 0.6)} />
      <motion.path d="M60 178h80" {...draw(r, delay + 0.7)} />
      <motion.path d="M70 164l-10 14M130 164l10 14" {...draw(r, delay + 0.65)} />
    </svg>
  );
};

/** Gavel — adjudication and verdict. */
export const GavelMark = ({ className = '', size = 64, title, delay = 0 }) => {
  const r = useReducedMotion();
  return (
    <svg {...svgProps(title, className, size)}>
      <motion.rect x="34" y="30" width="86" height="44" rx="6" transform="rotate(-38 77 52)" {...draw(r, delay)} />
      <motion.path d="M62 22 90 44M52 62 80 84" {...draw(r, delay + 0.25)} />
      <motion.path d="M96 76 152 132" {...draw(r, delay + 0.35)} />
      <motion.path d="M44 176h112" {...draw(r, delay + 0.5)} />
      <motion.rect x="60" y="156" width="80" height="16" rx="5" {...draw(r, delay + 0.55)} />
    </svg>
  );
};

/** Fluted column — the architecture of precedent. */
export const ColumnMark = ({ className = '', size = 64, title, delay = 0 }) => {
  const r = useReducedMotion();
  return (
    <svg {...svgProps(title, className, size)}>
      <motion.path d="M100 12 168 40H32z" {...draw(r, delay)} />
      <motion.path d="M40 40h120M34 56h132" {...draw(r, delay + 0.15)} />
      <motion.path d="M62 56v104M100 56v104M138 56v104" {...draw(r, delay + 0.3)} />
      <motion.path d="M34 160h132M28 176h144" {...draw(r, delay + 0.45)} />
    </svg>
  );
};

/** Bound volume — the archive. */
export const VolumeMark = ({ className = '', size = 64, title, delay = 0 }) => {
  const r = useReducedMotion();
  return (
    <svg {...svgProps(title, className, size)}>
      <motion.path d="M28 40a24 24 0 0 1 24-24h44v152H52a24 24 0 0 0-24 24z" {...draw(r, delay)} />
      <motion.path d="M172 40a24 24 0 0 0-24-24h-44v152h44a24 24 0 0 1 24 24z" {...draw(r, delay + 0.15)} />
      <motion.path d="M100 16v152" {...draw(r, delay + 0.35)} />
      <motion.path d="M50 60h30M50 84h30M120 60h30M120 84h30" {...draw(r, delay + 0.5)} />
    </svg>
  );
};

/** Verification seal — a slowly rotating ring around a static core. */
export const SealMark = ({ className = '', size = 120, title, spin = true }) => {
  const shouldReduce = useReducedMotion();
  const spinning = spin && !shouldReduce;

  return (
    <svg
      viewBox="0 0 240 240"
      width={size}
      height={size}
      fill="none"
      className={className}
      role={title ? 'img' : 'presentation'}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : 'true'}
    >
      <motion.g
        style={{ originX: '120px', originY: '120px' }}
        animate={spinning ? { rotate: 360 } : undefined}
        transition={spinning ? { duration: 60, ease: 'linear', repeat: Infinity } : undefined}
      >
        <circle cx="120" cy="120" r="112" stroke="currentColor" strokeOpacity=".5" strokeWidth="2" />
        <circle
          cx="120"
          cy="120"
          r="100"
          stroke="currentColor"
          strokeOpacity=".3"
          strokeWidth="1"
          strokeDasharray="3 8"
        />
        <g stroke="currentColor" strokeOpacity=".45" strokeWidth="2" strokeLinecap="round">
          <path d="M120 8v14M120 218v14M8 120h14M218 120h14" />
          <path d="M41 41l10 10M189 189l10 10M199 41l-10 10M51 189l-10 10" />
        </g>
      </motion.g>
      <g stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M120 84v66" />
        <circle cx="120" cy="80" r="5" fill="currentColor" stroke="none" />
        <path d="M84 98h72M84 98l-13 28h26zM156 98l13 28h-26z" />
        <path d="M71 126a13 13 0 0 0 26 0M143 126a13 13 0 0 0 26 0" />
        <path d="M104 150h32M96 162h48" />
      </g>
    </svg>
  );
};

export default ScalesMark;
