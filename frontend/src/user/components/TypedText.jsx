import { useReached, useTypewriter } from '../../lib/typing';

/**
 * Text that types itself in from time `at` (lib/typing.js), with a caret while
 * it does; nothing at all before its time, so the lines below the one being
 * typed are not on screen yet. `at` null: the whole text at once. Screen
 * readers get the whole text, not a letter at a time.
 */
const TypedText = ({ text, at = null, as: Tag = 'p', className = '' }) => {
  const { shown, started, done } = useTypewriter(text, at);
  if (!text || !started) return null;
  return (
    <Tag className={className}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {shown}
        {!done && <span className="typing-caret" />}
      </span>
    </Tag>
  );
};

/** Something that is not typed (a heading, labels, buttons): appears at `at`. */
export const Reveal = ({ at = null, children }) => (useReached(at) ? children : null);

/** "Fetching..." with dots that keep moving: something is happening. */
export const LoadingDots = ({ label, className = '' }) => (
  <span className={className} role="status">
    {label}
    <span className="loading-dots" aria-hidden="true">
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
  </span>
);

export default TypedText;
