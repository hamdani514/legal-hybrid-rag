import DOMPurify from 'dompurify';

/**
 * The single contract for rich text in this app.
 *
 * One side writes it (the blog editor, components/editor) and one side renders
 * it (the article page, user/blogs). Both import these lists, so a tag the
 * editor can produce is by construction a tag the reader will display — the
 * usual failure of hand-rolled editors is that the two drift and authors lose
 * formatting silently on publish.
 *
 * Stored HTML is author input, never trusted markup. It is sanitized on the
 * way out of the editor AND again before it is rendered, because the database
 * can also be written to by other means.
 */

export const ALLOWED_TAGS = [
  'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li', 'a', 'strong', 'em', 'b', 'i', 'u',
  's', 'sub', 'sup', 'blockquote', 'code', 'pre', 'br', 'hr', 'img', 'figure',
  'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div',
];

// `class` is deliberately absent. Nothing in the editor emits one, the
// article page styles by tag, and allowing it only lets foreign classes
// through — a Word paste arrives covered in `MsoNormal`.
export const ALLOWED_ATTR = [
  'href', 'title', 'target', 'rel', 'src', 'alt', 'width', 'height',
  'colspan', 'rowspan', 'style',
];

/**
 * `style` is allowed because an editor without alignment or colour is not an
 * editor — but only these properties, and only values matching these patterns.
 * Everything else is dropped. This is what keeps an author (or anyone who
 * reaches the database) from shipping `position:fixed` overlays, `url(...)`
 * callbacks or CSS escapes into a public page.
 */
const COLOR = /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%/]+\)|hsla?\([\d\s.,%/]+\)|[a-z]+)$/i;

const ALLOWED_STYLES = {
  'text-align': /^(left|center|right|justify)$/i,
  color: COLOR,
  'background-color': COLOR,
  'font-size': /^\d+(\.\d+)?(px|pt|em|rem|%)$/i,
  'font-family': /^[\w\s"',-]+$/,
  'font-weight': /^(normal|bold|lighter|bolder|[1-9]00)$/i,
  'font-style': /^(normal|italic)$/i,
  'text-decoration': /^(none|underline|line-through)$/i,
  width: /^\d+(\.\d+)?(px|%)$/i,
};

// Anything that can smuggle a value past the patterns above.
const STYLE_POISON = /url\s*\(|expression\s*\(|javascript:|@import|\\|\/\*/i;

const filterStyle = (declaration) => {
  if (!declaration || STYLE_POISON.test(declaration)) return '';

  return declaration
    .split(';')
    .map((part) => {
      const index = part.indexOf(':');
      if (index === -1) return null;
      const property = part.slice(0, index).trim().toLowerCase();
      const value = part.slice(index + 1).trim();
      const pattern = ALLOWED_STYLES[property];
      return pattern && pattern.test(value) ? `${property}: ${value}` : null;
    })
    .filter(Boolean)
    .join('; ');
};

/**
 * Parse `html` into a detached element. Detached so nothing in it can load,
 * run or render while we are working on it.
 */
export const parseFragment = (html) => {
  const parsed = new DOMParser().parseFromString(
    `<body><div data-rich-root>${html}</div></body>`,
    'text/html'
  );
  return parsed.querySelector('[data-rich-root]');
};

/**
 * Sanitize author HTML for storage or display.
 *
 * DOMPurify removes the dangerous structure; the second pass narrows `style`
 * to the property allowlist above, which DOMPurify deliberately does not do
 * for us — it blocks script, not layout abuse.
 */
export const sanitizeRichText = (html) => {
  if (!html) return '';

  const clean = DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
  const root = parseFragment(clean);
  if (!root) return clean;

  root.querySelectorAll('[style]').forEach((node) => {
    const safe = filterStyle(node.getAttribute('style'));
    if (safe) node.setAttribute('style', safe);
    else node.removeAttribute('style');
  });

  // A link that opens a new tab hands that tab a handle on this one unless it
  // is told otherwise, whatever the editor or the database said.
  root.querySelectorAll('a[target="_blank"]').forEach((anchor) => {
    anchor.setAttribute('rel', 'noopener noreferrer');
  });

  return root.innerHTML;
};

// contentEditable produces presentational tags; the stored document should be
// semantic, so these are rewritten on the way out.
const TAG_REWRITES = { B: 'strong', I: 'em', STRIKE: 's', DEL: 's', FONT: 'span' };

/**
 * Styles that mean a semantic tag.
 *
 * Browsers in CSS mode, and every pasted document, express emphasis as inline
 * CSS: `<span style="font-weight: bold">`. That renders bold but is not what
 * the text means — the article page styles `strong`, and a screen reader
 * announces it. Each match is lifted to the real tag and the declaration
 * dropped, so `font-weight: bold; color: red` becomes a red `<strong>`.
 */
const SEMANTIC_STYLES = [
  ['font-weight', (value) => /^(bold|bolder|[6-9]00)$/i.test(value.trim()), 'strong'],
  ['font-style', (value) => /^italic$/i.test(value.trim()), 'em'],
  ['text-decoration', (value) => /line-through/i.test(value), 's'],
  ['text-decoration-line', (value) => /line-through/i.test(value), 's'],
  ['text-decoration', (value) => /underline/i.test(value), 'u'],
  ['text-decoration-line', (value) => /underline/i.test(value), 'u'],
];

const promoteSemanticStyles = (root) => {
  root.querySelectorAll('span[style], p[style], div[style]').forEach((node) => {
    SEMANTIC_STYLES.forEach(([property, matches, tag]) => {
      const value = node.style.getPropertyValue(property);
      if (!value || !matches(value)) return;

      node.style.removeProperty(property);
      const wrapper = node.ownerDocument.createElement(tag);
      while (node.firstChild) wrapper.appendChild(node.firstChild);
      node.appendChild(wrapper);
    });

    if (!node.getAttribute('style')) node.removeAttribute('style');
  });
};

const rename = (node, tagName) => {
  const replacement = node.ownerDocument.createElement(tagName);
  Array.from(node.attributes).forEach((attribute) => {
    replacement.setAttribute(attribute.name, attribute.value);
  });
  while (node.firstChild) replacement.appendChild(node.firstChild);
  node.replaceWith(replacement);
  return replacement;
};

/**
 * Tidy what contentEditable leaves behind, then sanitize.
 *
 * Browsers emit `<b>`, `<font>` and bare `<div>` lines no matter how the
 * commands are issued. Storing that means the article page has to style two
 * tags for every one meaning, so it is normalized once here instead.
 */
export const normalizeRichText = (html) => {
  if (!html) return '';

  const root = parseFragment(html);
  if (!root) return '';

  // <b> -> <strong>, <i> -> <em>, <font> -> <span>, and so on.
  Object.entries(TAG_REWRITES).forEach(([from, to]) => {
    root.querySelectorAll(from.toLowerCase()).forEach((node) => rename(node, to));
  });

  // A top-level <div> is a paragraph the browser did not label.
  Array.from(root.children).forEach((child) => {
    if (child.tagName === 'DIV') rename(child, 'p');
  });

  // <font color> / <font size> predate CSS and DOMPurify keeps the attributes.
  root.querySelectorAll('span[color], span[size], span[face]').forEach((node) => {
    const declarations = [];
    if (node.getAttribute('color')) declarations.push(`color: ${node.getAttribute('color')}`);
    if (node.getAttribute('face')) declarations.push(`font-family: ${node.getAttribute('face')}`);
    node.removeAttribute('color');
    node.removeAttribute('size');
    node.removeAttribute('face');
    if (declarations.length) {
      node.setAttribute('style', [node.getAttribute('style'), ...declarations].filter(Boolean).join('; '));
    }
  });

  // font-weight: bold -> <strong>, and the rest of SEMANTIC_STYLES. Must run
  // before the bare-span sweep below, which clears up what it leaves behind.
  promoteSemanticStyles(root);

  // A <span> carrying no attributes carries no meaning — it is what is left
  // after a colour is cleared, or what a paste brought in for nothing.
  root.querySelectorAll('span').forEach((node) => {
    if (!node.attributes.length) node.replaceWith(...node.childNodes);
  });

  // Paragraphs the author emptied out while editing.
  root.querySelectorAll('p').forEach((node) => {
    if (node.textContent.trim() || node.querySelector('img, br, hr, table')) return;
    // A lone empty <p> is how an author leaves a blank line, so keep the last.
    if (node.parentElement === root && !node.nextElementSibling) return;
    node.remove();
  });

  return sanitizeRichText(root.innerHTML);
};

// Tags that end a line of text. Without this, textContent runs the end of one
// paragraph into the start of the next: "<h2>Alpha</h2><p>Beta</p>" reads as
// one word, which silently corrupts word counts, read times and excerpts.
const BLOCK_BOUNDARY = 'p, h2, h3, h4, li, blockquote, pre, tr, br, hr, div, figcaption';

/**
 * Plain text of a rich-text document, for excerpts, counts and search.
 */
export const richTextToPlain = (html) => {
  const root = parseFragment(sanitizeRichText(html));
  if (!root) return '';

  root.querySelectorAll(BLOCK_BOUNDARY).forEach((node) => {
    node.after(root.ownerDocument.createTextNode(' '));
  });

  return root.textContent.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
};

/**
 * Clean HTML arriving from the clipboard.
 *
 * Word, Google Docs and web pages carry the source document's typography with
 * them — `font-family: Calibri`, `font-size: 11pt`, white backgrounds. Those
 * properties are legitimate when an author picks them from the toolbar, so
 * they are not banned outright; they are stripped here, where we know the
 * content came from somewhere else and should adopt the article's own styling.
 */
export const cleanPastedHtml = (html) => {
  const root = parseFragment(normalizeRichText(html));
  if (!root) return '';

  root.querySelectorAll('[style]').forEach((node) => {
    const kept = node
      .getAttribute('style')
      .split(';')
      .filter((part) => {
        const property = part.split(':')[0]?.trim().toLowerCase();
        return property && !['font-family', 'font-size', 'background-color', 'color'].includes(property);
      })
      .join(';')
      .trim();

    if (kept) node.setAttribute('style', kept);
    else node.removeAttribute('style');
  });

  // Word pads paragraphs with non-breaking spaces — a whole empty one where
  // it had a spacer element, and a leading one where a tag was stripped out.
  root.querySelectorAll('p').forEach((node) => {
    if (!node.textContent.replace(/\u00a0/g, '').trim() && !node.querySelector('img, table')) {
      node.remove();
      return;
    }
    const first = node.firstChild;
    if (first?.nodeType === 3) {
      first.textContent = first.textContent.replace(/^[\u00a0\s]+/, '');
    }
  });

  // Back through normalize: stripping the styles above leaves spans that now
  // carry no attributes, and those are exactly what normalize unwraps.
  return normalizeRichText(root.innerHTML);
};

export const countWords = (html) => {
  const text = richTextToPlain(html);
  return text ? text.split(/\s+/).length : 0;
};
