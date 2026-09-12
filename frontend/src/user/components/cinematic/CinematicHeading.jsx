import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { EASE_OUT_EXPO, VIEWPORT_SOFT, wordReveal } from '../../motion';

/**
 * Headline that resolves word by word, like a film title card.
 *
 * Pass `text` as a string; use "|" to force a line break. Each word gets its
 * own overflow-clipped track so the letters rise out of an invisible baseline.
 * Under reduced motion the whole heading simply fades in as one block.
 */
const CinematicHeading = ({
  text,
  as: Tag = 'h2',
  className = '',
  delay = 0,
  stagger = 0.07,
  trigger = 'load', // 'load' | 'scroll'
  accentFrom,       // index of the first word rendered in gold
  ...rest           // id, aria-*, anything the heading element needs
}) => {
  const shouldReduce = useReducedMotion();
  // `motion[tag]` is cached by the proxy, so the component identity is stable
  // across renders — building it with motion.create() here would remount the node.
  const MotionTag = motion[Tag];

  // Pre-compute each line's starting word index so `accentFrom` can be
  // resolved without mutating a counter during render.
  const lines = String(text).split('|').map((line) => line.trim().split(/\s+/));
  const lineOffsets = lines.reduce(
    (acc, line) => [...acc, acc[acc.length - 1] + line.length],
    [0]
  );

  if (shouldReduce) {
    return (
      <MotionTag
        className={className}
        {...rest}
        initial={{ opacity: 0 }}
        {...(trigger === 'scroll'
          ? { whileInView: { opacity: 1 }, viewport: VIEWPORT_SOFT }
          : { animate: { opacity: 1 } })}
        transition={{ duration: 0.3 }}
      >
        {lines.map((line, i) => (
          <React.Fragment key={i}>
            {i > 0 && <br />}
            {line.join(' ')}
          </React.Fragment>
        ))}
      </MotionTag>
    );
  }

  return (
    <MotionTag
      className={className}
      {...rest}
      style={{ perspective: 800 }}
      initial="hidden"
      {...(trigger === 'scroll'
        ? { whileInView: 'show', viewport: VIEWPORT_SOFT }
        : { animate: 'show' })}
      transition={{ staggerChildren: stagger, delayChildren: delay }}
    >
      {lines.map((line, lineIdx) => (
        <span key={lineIdx} className="block">
          {line.map((word, i) => {
            const wordIndex = lineOffsets[lineIdx] + i;
            const isAccent = accentFrom !== undefined && wordIndex >= accentFrom;
            return (
              <span
                key={`${word}-${wordIndex}`}
                className="inline-block overflow-hidden align-bottom pb-[0.12em] pr-[0.26em]"
              >
                <motion.span
                  className={`inline-block ${isAccent ? 'text-gradient-gold' : ''}`}
                  variants={wordReveal}
                  style={{ transformOrigin: 'bottom center' }}
                >
                  {word}
                </motion.span>
              </span>
            );
          })}
        </span>
      ))}
    </MotionTag>
  );
};

/** Small uppercase kicker above a headline, with a gold tick that draws in. */
export const Eyebrow = ({ children, className = '', delay = 0, tone = 'gold' }) => {
  const shouldReduce = useReducedMotion();
  // #8F6B28 clears 4.5:1 on parchment; the pale gold does not.
  const toneClass = tone === 'gold' ? 'text-gold-700' : 'text-ink-500';

  return (
    <motion.span
      className={`inline-flex items-center gap-3 font-body text-[10px] sm:text-xs font-semibold uppercase tracking-[0.32em] ${toneClass} ${className}`}
      initial={{ opacity: 0, y: shouldReduce ? 0 : 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: EASE_OUT_EXPO, delay }}
    >
      <motion.span
        aria-hidden="true"
        className="h-px w-8 origin-left bg-gold-600"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.7, ease: EASE_OUT_EXPO, delay: delay + 0.1 }}
      />
      {children}
    </motion.span>
  );
};

export default CinematicHeading;
