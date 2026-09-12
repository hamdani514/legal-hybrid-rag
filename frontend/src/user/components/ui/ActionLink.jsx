import React from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { EASE_OUT_EXPO } from '../../motion';

/**
 * One call-to-action, three shells.
 *
 * Renders a react-router <Link> for in-app routes, an <a> for external/mailto
 * targets, and a <button> when there is no destination — so every CTA on the
 * site is a real, keyboard-reachable navigation instead of a dead <button>.
 */

const VARIANTS = {
  // Gold foil — the single highest-intent action on a screen. Ink text on
  // gold clears 8:1, so the label stays legible at button size.
  gold:
    'bg-gradient-to-r from-gold-400 via-gold-300 to-gold-500 text-ink-900 shadow-gold hover:shadow-[0_20px_38px_-16px_rgba(185,140,54,0.55)]',
  // Ink — the standard primary on parchment
  ink:
    'bg-ink-800 text-white shadow-lifted hover:bg-ink-900 hover:shadow-[0_20px_38px_-18px_rgba(13,28,50,0.5)]',
  // Outline — secondary weight, still fully readable
  outline:
    'border border-ink-800/25 text-ink-800 hover:border-gold-600 hover:bg-gold-50',
  // Ghost — the lightest button; gold rim, ink label
  ghost:
    'border border-gold-600/45 text-ink-800 hover:border-gold-600 hover:bg-gold-50',
  // Inline text action with a wiping gold underline
  text: 'text-gold-700 hover:text-gold-800 link-wipe px-0 py-1',
};

const SIZES = {
  sm: 'px-5 py-2.5 text-xs tracking-[0.14em]',
  md: 'px-7 py-3.5 text-sm tracking-[0.12em]',
  lg: 'px-8 py-4 text-sm sm:text-base tracking-[0.1em]',
};

const ActionLink = ({
  to,
  href,
  onClick,
  type = 'button',
  variant = 'ink',
  size = 'md',
  icon = 'arrow_forward',
  iconPosition = 'end',
  disabled = false,
  className = '',
  children,
  ...rest
}) => {
  const shouldReduce = useReducedMotion();
  const isText = variant === 'text';

  const base = [
    'group relative inline-flex shrink-0 items-center justify-center gap-2.5 whitespace-nowrap rounded-lg font-body font-semibold',
    // The inline text variant sits inside running copy, so it keeps sentence case
    isText ? 'text-inherit' : 'uppercase',
    'transition-[box-shadow,background-color,border-color,color] duration-300',
    'disabled:cursor-not-allowed disabled:opacity-60',
    isText ? 'rounded-none' : `${SIZES[size]} btn-sheen`,
    VARIANTS[variant],
    className,
  ].join(' ');

  const content = (
    <>
      {icon && iconPosition === 'start' && (
        <span
          aria-hidden="true"
          className="material-symbols-outlined text-base transition-transform duration-300 group-hover:-translate-x-0.5"
        >
          {icon}
        </span>
      )}
      <span className="relative z-[2]">{children}</span>
      {icon && iconPosition === 'end' && (
        <span
          aria-hidden="true"
          className="material-symbols-outlined relative z-[2] text-base transition-transform duration-300 group-hover:translate-x-1"
        >
          {icon}
        </span>
      )}
    </>
  );

  const hover = shouldReduce || disabled ? undefined : { y: -3 };
  const tap = shouldReduce || disabled ? undefined : { y: 0, scale: 0.985 };
  const transition = { duration: 0.28, ease: EASE_OUT_EXPO };

  // In-app route
  if (to && !disabled) {
    return (
      <motion.span className="inline-flex" whileHover={hover} whileTap={tap} transition={transition}>
        <Link to={to} onClick={onClick} className={base} {...rest}>
          {content}
        </Link>
      </motion.span>
    );
  }

  // External link / mailto / tel
  if (href && !disabled) {
    const external = /^https?:/i.test(href);
    return (
      <motion.span className="inline-flex" whileHover={hover} whileTap={tap} transition={transition}>
        <a
          href={href}
          className={base}
          {...(external ? { target: '_blank', rel: 'noreferrer noopener' } : {})}
          {...rest}
        >
          {content}
        </a>
      </motion.span>
    );
  }

  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={base}
      whileHover={hover}
      whileTap={tap}
      transition={transition}
      {...rest}
    >
      {content}
    </motion.button>
  );
};

export default ActionLink;
