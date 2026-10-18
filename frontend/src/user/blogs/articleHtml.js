import { parseFragment, sanitizeRichText } from '../../lib/richText';

/**
 * Turns the stored article body into something safe to render, plus the
 * "On this page" rail that goes beside it.
 *
 * The allowlist itself lives in lib/richText.js, shared with the editor that
 * writes these articles — see the note there. Sanitizing happens again here
 * rather than being trusted from write time, because the database is not the
 * only way content can arrive.
 */

const slugify = (text) =>
  text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'section';

/**
 * @param {string} html the stored article body
 * @returns {{ html: string, toc: Array<{ id: string, label: string }> }}
 */
export const prepareArticle = (html) => {
  if (!html) return { html: '', toc: [] };

  const clean = sanitizeRichText(html);

  // Parsed rather than regexed so a heading containing markup still yields a
  // clean label, and so ids land on the real elements the rail scrolls to.
  const root = parseFragment(clean);
  if (!root) return { html: clean, toc: [] };

  const toc = [];
  const used = new Set();

  root.querySelectorAll('h2').forEach((heading) => {
    const label = heading.textContent.trim();
    if (!label) return;

    // Two sections may share a title; the rail still needs one target each.
    const base = slugify(label);
    let id = base;
    let suffix = 2;
    while (used.has(id)) {
      id = `${base}-${suffix}`;
      suffix += 1;
    }
    used.add(id);

    heading.setAttribute('id', id);
    toc.push({ id, label });
  });

  return { html: root.innerHTML, toc };
};

export default prepareArticle;
