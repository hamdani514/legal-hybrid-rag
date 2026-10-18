/**
 * The command layer between the toolbar and the contentEditable surface.
 *
 * It is built on document.execCommand. That API is marked obsolete, and it is
 * worth being clear why it is still the right choice here: every browser
 * implements it, it is the only built-in way to split, merge and re-wrap
 * ranges across arbitrary selections, and the alternative is a document model
 * and a layout engine — which is what ProseMirror and Lexical are. Keeping
 * every call behind this module means the editor can be re-based on one of
 * those later without the toolbar, dialogs or admin pages changing.
 *
 * Nothing here reads or writes React state; the component owns that.
 */

/** Browsers differ on which of these exists; try each and report success. */
const run = (command, value = null) => {
  try {
    return document.execCommand(command, false, value);
  } catch {
    return false;
  }
};

/**
 * execCommand emits `<div>` line breaks unless told to use paragraphs.
 *
 * styleWithCSS is left OFF deliberately. With it on, Bold produces
 * `<span style="font-weight: bold">` rather than `<b>` — which renders bold
 * but is not semantic, loses the article page's `strong` styling, and reads as
 * plain text to a screen reader. Off, Bold gives `<b>` and normalizeRichText
 * promotes it to `<strong>`. The few commands that genuinely need CSS turn it
 * on just for themselves, via withCSS below.
 */
export const configureDocument = () => {
  run('styleWithCSS', false);
  run('defaultParagraphSeparator', 'p');
};

/** Run one command with CSS output, then restore the semantic default. */
const withCSS = (fn) => {
  run('styleWithCSS', true);
  try {
    return fn();
  } finally {
    run('styleWithCSS', false);
  }
};

export const exec = run;

export const queryState = (command) => {
  try {
    return document.queryCommandState(command);
  } catch {
    return false;
  }
};

export const queryValue = (command) => {
  try {
    return document.queryCommandValue(command);
  } catch {
    return '';
  }
};

// ── Selection ────────────────────────────────────────────────────────────

export const getSelection = () => window.getSelection();

export const getRange = () => {
  const selection = window.getSelection();
  return selection && selection.rangeCount ? selection.getRangeAt(0) : null;
};

/**
 * Opening a dialog moves focus out of the editable area, which collapses the
 * selection the dialog is about to act on. Callers save the range first and
 * restore it before issuing the command.
 */
export const saveRange = () => {
  const range = getRange();
  return range ? range.cloneRange() : null;
};

export const restoreRange = (range) => {
  if (!range) return;
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
};

export const isWithin = (root, node) => Boolean(root && node && root.contains(node));

/** True when the caret is inside the given editable root. */
export const selectionInside = (root) => {
  const range = getRange();
  return Boolean(range && isWithin(root, range.commonAncestorContainer));
};

/** The nearest element to the caret, walking out of text nodes. */
export const selectedElement = (root) => {
  const range = getRange();
  if (!range) return null;
  let node = range.startContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
  return isWithin(root, node) ? node : null;
};

/** The nearest ancestor matching `selector`, bounded by the editable root. */
export const closestWithin = (root, selector) => {
  const node = selectedElement(root);
  if (!node) return null;
  const match = node.closest(selector);
  return match && isWithin(root, match) ? match : null;
};

const BLOCK_TAGS = ['h2', 'h3', 'h4', 'blockquote', 'pre', 'li', 'p'];

/**
 * Which block the caret sits in, as a lowercase tag name. Drives the
 * "Paragraph / Heading 2 / …" select in the toolbar.
 */
export const currentBlock = (root) => {
  const block = closestWithin(root, BLOCK_TAGS.join(','));
  return block ? block.tagName.toLowerCase() : 'p';
};

// ── Formatting ───────────────────────────────────────────────────────────

export const toggleInline = (command) => run(command);

/**
 * Set the block type of the caret's paragraph.
 *
 * Browsers disagree on the argument: Firefox historically wanted the tag in
 * angle brackets, Chrome accepts both. Both forms are attempted.
 */
export const setBlock = (tag) => {
  if (!run('formatBlock', `<${tag}>`)) run('formatBlock', tag);
};

export const setAlignment = (alignment) => {
  const commands = {
    left: 'justifyLeft',
    center: 'justifyCenter',
    right: 'justifyRight',
    justify: 'justifyFull',
  };
  run(commands[alignment] || 'justifyLeft');
};

export const setColor = (color) => withCSS(() => run('foreColor', color));

export const setHighlight = (color) =>
  withCSS(() => {
    // hiliteColor is the standard; Chrome has historically only honoured
    // backColor when styleWithCSS is on.
    if (!run('hiliteColor', color)) run('backColor', color);
  });

export const setFontFamily = (family) => withCSS(() => run('fontName', family));

/**
 * execCommand('fontSize') only accepts the 1-7 HTML font scale, which cannot
 * express "19px". The selection is wrapped with a known marker size, and those
 * nodes are then rewritten to spans carrying a real CSS font-size.
 *
 * This needs the NON-CSS output: with styleWithCSS on the command produces
 * `font-size: xxx-large` and no marker attribute to find it by.
 */
export const setFontSize = (size, root) => {
  run('fontSize', '7');
  if (!root) return;

  root.querySelectorAll('[size="7"]').forEach((node) => {
    const span = node.ownerDocument.createElement('span');
    span.style.fontSize = size;
    // Carry across anything else the command left on the node.
    if (node.getAttribute('style')) span.setAttribute('style', `${node.getAttribute('style')}; font-size: ${size}`);
    while (node.firstChild) span.appendChild(node.firstChild);
    node.replaceWith(span);
  });
};

const INLINE_COMMANDS = ['bold', 'italic', 'underline', 'strikeThrough', 'subscript', 'superscript'];

export const clearFormatting = (root) => {
  const collapsed = getRange()?.collapsed;

  run('removeFormat');

  // With nothing selected, removeFormat does not clear the PENDING state in
  // Chrome: the next characters typed still come out bold, because formatting
  // carries across a line break. Each active format is switched off by hand so
  // "clear formatting" means the same thing with or without a selection.
  if (collapsed) {
    INLINE_COMMANDS.forEach((command) => {
      if (queryState(command)) run(command);
    });
  }

  // removeFormat leaves block-level choices alone, which is usually not what
  // "clear formatting" means to an author staring at a heading.
  const block = closestWithin(root, 'h2,h3,h4,blockquote,pre');
  if (block) setBlock('p');
};

// ── Insertions ───────────────────────────────────────────────────────────

export const insertHTML = (html) => {
  if (!run('insertHTML', html)) {
    const range = getRange();
    if (!range) return;
    const fragment = range.createContextualFragment(html);
    range.deleteContents();
    range.insertNode(fragment);
  }
};

export const insertLink = ({ url, text, newTab }) => {
  const safeUrl = normalizeUrl(url);
  if (!safeUrl) return;

  const range = getRange();
  const collapsed = !range || range.collapsed;
  const label = (text || '').trim() || safeUrl;
  const attributes = newTab ? ' target="_blank" rel="noopener noreferrer"' : '';

  if (collapsed || text) {
    insertHTML(`<a href="${escapeAttribute(safeUrl)}"${attributes}>${escapeText(label)}</a>`);
    return;
  }

  run('createLink', safeUrl);
  const anchor = closestWithin(document.body, 'a');
  if (anchor && newTab) {
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  }
};

export const removeLink = () => run('unlink');

export const insertImage = ({ src, alt, caption }) => {
  const safeSrc = normalizeUrl(src);
  if (!safeSrc) return;

  const image = `<img src="${escapeAttribute(safeSrc)}" alt="${escapeAttribute(alt || '')}">`;
  insertHTML(
    caption
      ? `<figure>${image}<figcaption>${escapeText(caption)}</figcaption></figure><p><br></p>`
      : `${image}<p><br></p>`
  );
};

export const insertTable = ({ rows, columns, header }) => {
  const cell = (tag) => `<${tag}><br></${tag}>`;
  const body = Array.from({ length: rows }, () =>
    `<tr>${Array.from({ length: columns }, () => cell('td')).join('')}</tr>`
  ).join('');
  const head = header
    ? `<thead><tr>${Array.from({ length: columns }, () => cell('th')).join('')}</tr></thead>`
    : '';

  insertHTML(`<table>${head}<tbody>${body}</tbody></table><p><br></p>`);
};

export const insertRule = () => insertHTML('<hr><p><br></p>');

// ── URL and text safety ──────────────────────────────────────────────────

const SAFE_PROTOCOL = /^(https?:|mailto:|tel:|#|\/)/i;

/**
 * Accept only protocols that cannot execute. A bare "example.com" is treated
 * as https rather than rejected, because that is what an author means.
 */
export const normalizeUrl = (value) => {
  const url = (value || '').trim();
  if (!url) return '';
  if (SAFE_PROTOCOL.test(url)) return url;
  // Anything with a scheme we did not allow — javascript:, data:, vbscript: —
  // is refused rather than coerced.
  if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return '';
  return `https://${url}`;
};

export const escapeText = (text) =>
  String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export const escapeAttribute = (text) => escapeText(text).replace(/"/g, '&quot;');
