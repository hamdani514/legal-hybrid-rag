import { useEffect, useState } from 'react';

/*
 * The typing effect for new answers: an answer is written out top to bottom,
 * line by line, as if the AI were typing it.
 *
 * One timeline per answer. markFresh() records WHEN a reply (or a page of
 * "more" cases) arrived; every line of it is given a start time on that
 * clock (ResultsPanel's schedules), appears only when its time comes, and
 * types in; nothing below it is on screen yet. A conversation reopened from
 * history is loaded as new objects, so it has no time and shows at once.
 * Nothing is stored on the reply (it is saved to the server as it is).
 *
 * Times are performance.now() milliseconds, the clock requestAnimationFrame
 * uses. People who ask their system for reduced motion see text at once.
 */

const freshTimes = new WeakMap();

/** Record that `obj` arrived now (or at `at`): it types itself in. */
export const markFresh = (obj, at = performance.now()) => {
  if (obj && typeof obj === 'object') freshTimes.set(obj, at);
  return obj;
};

/** When `obj` arrived, or null when it did not arrive in this visit. */
export const freshAt = (obj) => (obj && typeof obj === 'object' ? (freshTimes.get(obj) ?? null) : null);

export const isFresh = (obj) => freshAt(obj) !== null;

const MS_PER_CHAR = 4;
const MIN_MS = 120;
const MAX_MS = 1300;
/** A line that is not typed (a heading, labels, buttons) appears, then this pause. */
export const REVEAL_MS = 140;

/** How long one block of text takes to type (0 for no text). */
export const typeDuration = (text) => {
  const n = String(text || '').length;
  return n ? Math.min(MAX_MS, Math.max(MIN_MS, n * MS_PER_CHAR)) : 0;
};

const reducedMotion = () => {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
};

const now = () => performance.now();

/**
 * Whether time `at` has come (true at once for null: nothing to wait for).
 * State changes only in the timer, when the time comes.
 */
export const useReached = (at) => {
  const waiting = at !== null && at !== undefined && !reducedMotion();
  const [reachedAt, setReachedAt] = useState(() => (waiting && now() < at ? null : at));
  useEffect(() => {
    if (!waiting || reachedAt === at) return undefined;
    const timer = setTimeout(() => setReachedAt(at), Math.max(0, at - now()));
    return () => clearTimeout(timer);
  }, [at, waiting, reachedAt]);
  return !waiting || reachedAt === at || now() >= at;
};

/**
 * The part of `text` typed so far: { shown, started, done }. `at` is when
 * typing starts (null: the whole text at once).
 */
export const useTypewriter = (text, at = null) => {
  const full = String(text ?? '');
  const animate = at !== null && at !== undefined && full.length > 0 && !reducedMotion();
  // How far the CURRENT text has typed; only animation frames update it.
  const [progress, setProgress] = useState({ text: '', count: 0, started: false });

  useEffect(() => {
    if (!animate) return undefined;
    const total = full.length;
    const duration = typeDuration(full);
    let frame;
    const tick = (time) => {
      const share = (time - at) / duration;
      if (share >= 0) {
        setProgress({ text: full, count: Math.min(total, Math.ceil(share * total)), started: true });
      }
      if (share < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [full, animate, at]);

  if (!animate) return { shown: full, started: true, done: true };
  if (progress.text !== full) {
    // Before the first frame: already past (e.g. scrolled back) or not yet.
    const past = now() >= at + typeDuration(full);
    return { shown: past ? full : '', started: past, done: past };
  }
  return { shown: full.slice(0, progress.count), started: progress.started, done: progress.count >= full.length };
};
