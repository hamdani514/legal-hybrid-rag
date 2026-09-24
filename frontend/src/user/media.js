/**
 * The photographic library, in one place.
 *
 * Every photograph used anywhere in the public site is declared here with its
 * intrinsic size, a written alt text, and a `focus` point. Components import
 * from this module rather than writing `/assets/…` inline, so a replaced file
 * or a re-crop is a one-line change instead of a grep.
 *
 * `w`/`h` are the file's real pixel dimensions — passed to <img> so the
 * browser reserves the box before the bytes land and the page never jumps.
 * `focus` is the object-position to hold when a frame crops the image; it is
 * chosen per photograph, because a centre crop cuts the Supreme Court's
 * portico in half and decapitates the scales in asset2.
 *
 * `tone` says whether the photograph is dark enough to carry white text on
 * its own ('dark') or needs the ink wash turned up ('light').
 */

const BASE = '/assets';

export const MEDIA = {
  /** The Supreme Court of Pakistan building, with the approach sign. */
  court: {
    src: `${BASE}/supremecourt.jpg`,
    w: 735,
    h: 552,
    ratio: 735 / 552,
    focus: '50% 42%',
    tone: 'light',
    alt: 'The Supreme Court of Pakistan building in Islamabad, seen from its approach road.',
  },

  /** Gavel resting on a bench in front of the flag of Pakistan. */
  bench: {
    src: `${BASE}/asset1.jpg`,
    w: 940,
    h: 475,
    ratio: 940 / 475,
    focus: '38% 55%',
    tone: 'dark',
    alt: 'A wooden gavel on a bench, with the flag of Pakistan behind it.',
  },

  /** Brass scales and a gavel before a wall of bound law reports. */
  scales: {
    src: `${BASE}/asset2.jpg`,
    w: 736,
    h: 1041,
    ratio: 736 / 1041,
    focus: '58% 40%',
    tone: 'dark',
    alt: 'Brass scales of justice and a gavel on a desk, in front of shelved law reports.',
  },

  /** Scales beside a printed judgment and an open laptop. */
  desk: {
    src: `${BASE}/asset3.jpg`,
    w: 736,
    h: 1104,
    ratio: 736 / 1104,
    focus: '42% 48%',
    tone: 'dark',
    alt: 'Brass scales beside a printed judgment and an open laptop on a chamber desk.',
  },

  /** Shelves of bound volumes — the corpus, physically. */
  stacks: {
    src: `${BASE}/assets4.jpg`,
    w: 676,
    h: 1200,
    ratio: 676 / 1200,
    focus: '50% 38%',
    tone: 'dark',
    alt: 'Floor-to-ceiling shelves of bound volumes in a law library, with stacks on the table below.',
  },

  /** A gavel laid across the open pages of a volume. */
  volume: {
    src: `${BASE}/asset5.jpg`,
    w: 736,
    h: 736,
    ratio: 1,
    focus: '50% 50%',
    tone: 'light',
    alt: 'A gavel and its block resting on the open pages of a bound volume.',
  },
};

/**
 * These files top out at 1200px on the long edge. Anything that scales one
 * past that — a true full-bleed hero at desktop width — reads soft, so the
 * full-bleed bands below deliberately cap their height and run a gradient
 * wash over the photograph, which is where the softness stops being visible.
 */
export const MAX_SOURCE_EDGE = 1200;

export default MEDIA;
