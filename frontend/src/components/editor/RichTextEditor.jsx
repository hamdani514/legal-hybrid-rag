import { useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import EditorToolbar from './EditorToolbar';
import EditorDialog, { DialogField, dialogInputClass } from './EditorDialog';
import { cleanPastedHtml, countWords, normalizeRichText, sanitizeRichText } from '../../lib/richText';
import * as cmd from './editorCommands';
import './editor.css';

const EMPTY = '<p><br></p>';

/**
 * Publish whether the document is blank, for the placeholder.
 *
 * This cannot be done with CSS :empty — an empty contentEditable document is
 * `<p><br></p>`, which has a child node and never matches. The state is
 * written to a data attribute and editor.css keys off that.
 */
const syncEmptyState = (node) => {
  if (!node) return;
  const blank = !node.textContent.trim() && !node.querySelector('img, table, hr');
  node.dataset.empty = blank ? 'true' : 'false';
};

/**
 * A rich-text editor that stores HTML.
 *
 * What it produces is exactly what the article page renders: the tag and style
 * allowlists live in lib/richText.js and are shared by both sides, so an
 * author never formats something that silently disappears on publish.
 *
 * Contract:
 *   value     — HTML string. Treated as the initial document and as an
 *               external reset; it is NOT written back into the DOM on every
 *               keystroke, which is what makes the caret stay put.
 *   onChange  — called with sanitized HTML as the author types.
 *   ref       — exposes getHTML() returning the normalized document, for a
 *               parent that wants the tidied version at save time.
 *
 * The commands behind the toolbar are in editorCommands.js; see the note there
 * on why this is built on execCommand.
 */
const RichTextEditor = ({
  value = '',
  onChange,
  ref,
  placeholder = 'Write the article…',
  minHeight = 460,
}) => {
  const editorRef = useRef(null);
  const containerRef = useRef(null);
  // The last HTML this component emitted. Incoming `value` is only written
  // into the DOM when it differs from this, which is how an external reset is
  // told apart from the echo of our own onChange.
  const emitted = useRef(value);
  const savedRange = useRef(null);
  // The caret's last known position inside the editable area. The toolbar's
  // <select> controls take focus when clicked, which collapses the selection
  // before the command runs; every command restores from here first.
  const liveRange = useRef(null);
  // HTML coming back from source view, waiting for the editable div to exist.
  // While source mode is on that div is unmounted, so it cannot be written to
  // until React has re-rendered — see the effect that drains this.
  const pendingFromSource = useRef(null);

  const [sourceMode, setSourceMode] = useState(false);
  const [sourceText, setSourceText] = useState('');
  const [fullscreen, setFullscreen] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [form, setForm] = useState({});
  const [state, setState] = useState({ block: 'p' });

  // ── Document in / out ──────────────────────────────────────────────────

  useEffect(() => {
    const node = editorRef.current;
    if (!node || sourceMode) return;
    // Content returning from source view is applied by the effect below, which
    // must win over the parent's not-yet-updated `value`.
    if (pendingFromSource.current !== null) return;

    if (value !== emitted.current) {
      node.innerHTML = sanitizeRichText(value) || EMPTY;
      emitted.current = value;
      syncEmptyState(node);
    }
  }, [value, sourceMode]);

  /**
   * Put the source-view document into the editable div once it is back.
   *
   * Leaving source mode unmounts the textarea and mounts the div in the same
   * commit, so at the moment the toolbar handler runs there is no editable
   * node to write to — editorRef.current is null and the edit is silently
   * dropped. This runs after that commit, when the node exists.
   */
  useEffect(() => {
    if (sourceMode || pendingFromSource.current === null) return;
    const node = editorRef.current;
    if (!node) return;

    node.innerHTML = pendingFromSource.current || EMPTY;
    syncEmptyState(node);
    pendingFromSource.current = null;
  }, [sourceMode]);

  useEffect(() => {
    cmd.configureDocument();
    const node = editorRef.current;
    if (node && !node.innerHTML) node.innerHTML = sanitizeRichText(value) || EMPTY;
    syncEmptyState(node);
    // Mount only: `value` is handled by the effect above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emit = useCallback(() => {
    const node = editorRef.current;
    if (!node) return;
    syncEmptyState(node);
    const html = sanitizeRichText(node.innerHTML);
    emitted.current = html;
    onChange?.(html);
  }, [onChange]);

  useImperativeHandle(ref, () => ({
    getHTML: () => {
      if (sourceMode) return normalizeRichText(sourceText);
      return normalizeRichText(editorRef.current?.innerHTML || '');
    },
    focus: () => editorRef.current?.focus(),
  }));

  // ── Toolbar state ──────────────────────────────────────────────────────

  const refreshState = useCallback(() => {
    const node = editorRef.current;
    if (!node || sourceMode || !cmd.selectionInside(node)) return;

    // Remembered while the caret is still ours, so a toolbar control that
    // takes focus can put it back exactly where the author left it.
    liveRange.current = cmd.saveRange();

    setState({
      bold: cmd.queryState('bold'),
      italic: cmd.queryState('italic'),
      underline: cmd.queryState('underline'),
      strike: cmd.queryState('strikeThrough'),
      superscript: cmd.queryState('superscript'),
      subscript: cmd.queryState('subscript'),
      bulleted: cmd.queryState('insertUnorderedList'),
      numbered: cmd.queryState('insertOrderedList'),
      alignLeft: cmd.queryState('justifyLeft'),
      alignCenter: cmd.queryState('justifyCenter'),
      alignRight: cmd.queryState('justifyRight'),
      alignJustify: cmd.queryState('justifyFull'),
      link: Boolean(cmd.closestWithin(node, 'a')),
      block: cmd.currentBlock(node),
    });
  }, [sourceMode]);

  useEffect(() => {
    document.addEventListener('selectionchange', refreshState);
    return () => document.removeEventListener('selectionchange', refreshState);
  }, [refreshState]);

  // ── Actions ────────────────────────────────────────────────────────────

  const openDialog = (name, initial) => {
    savedRange.current = cmd.saveRange();
    setForm(initial);
    setDialog(name);
  };

  const closeDialog = () => {
    setDialog(null);
    editorRef.current?.focus();
    cmd.restoreRange(savedRange.current);
  };

  const withSelection = (fn) => {
    editorRef.current?.focus();
    cmd.restoreRange(savedRange.current);
    fn();
    emit();
    refreshState();
  };

  const handleAction = (action, actionValue) => {
    const node = editorRef.current;

    if (action === 'source') {
      if (sourceMode) {
        // Coming back from source: the typed HTML is author input like any
        // other, so it is sanitized before it is trusted as a document. The
        // editable div does not exist yet — it mounts in this same commit —
        // so the DOM write is handed to the effect above.
        const html = normalizeRichText(sourceText);
        pendingFromSource.current = html;
        emitted.current = html;
        setSourceMode(false);
        onChange?.(html);
      } else {
        setSourceText(normalizeRichText(node?.innerHTML || ''));
        setSourceMode(true);
      }
      return;
    }

    if (action === 'fullscreen') {
      setFullscreen((current) => !current);
      return;
    }

    if (sourceMode) return;

    // The <select> controls and the colour picker take focus to open, which
    // collapses the selection the command is about to act on. Buttons avoid
    // this with preventDefault on mousedown; these cannot, so the caret is
    // restored from the last position seen inside the editor.
    node?.focus();
    cmd.restoreRange(liveRange.current);

    switch (action) {
      case 'bold': cmd.toggleInline('bold'); break;
      case 'italic': cmd.toggleInline('italic'); break;
      case 'underline': cmd.toggleInline('underline'); break;
      case 'strike': cmd.toggleInline('strikeThrough'); break;
      case 'superscript': cmd.toggleInline('superscript'); break;
      case 'subscript': cmd.toggleInline('subscript'); break;
      case 'block': cmd.setBlock(actionValue); break;
      case 'font': if (actionValue) cmd.setFontFamily(actionValue); break;
      case 'size': if (actionValue) cmd.setFontSize(actionValue, node); break;
      case 'color': cmd.setColor(actionValue); break;
      case 'highlight':
        cmd.setHighlight(actionValue === 'transparent' ? 'inherit' : actionValue);
        break;
      case 'bulleted': cmd.exec('insertUnorderedList'); break;
      case 'numbered': cmd.exec('insertOrderedList'); break;
      case 'indent': cmd.exec('indent'); break;
      case 'outdent': cmd.exec('outdent'); break;
      case 'align': cmd.setAlignment(actionValue); break;
      case 'unlink': cmd.removeLink(); break;
      case 'rule': cmd.insertRule(); break;
      case 'clear': cmd.clearFormatting(node); break;
      case 'undo': cmd.exec('undo'); break;
      case 'redo': cmd.exec('redo'); break;

      case 'link': {
        const anchor = cmd.closestWithin(node, 'a');
        const selected = window.getSelection()?.toString() || '';
        openDialog('link', {
          url: anchor?.getAttribute('href') || '',
          text: anchor?.textContent || selected,
          newTab: anchor?.getAttribute('target') === '_blank',
        });
        return;
      }
      case 'image':
        openDialog('image', { src: '', alt: '', caption: '' });
        return;
      case 'table':
        openDialog('table', { rows: 3, columns: 3, header: true });
        return;

      default:
        return;
    }

    emit();
    refreshState();
  };

  // ── Keyboard and paste ─────────────────────────────────────────────────

  const handleKeyDown = (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();

    // Ctrl+K is the one shortcut the browser does not already provide.
    if (key === 'k') {
      event.preventDefault();
      handleAction('link');
      return;
    }
    // b/i/u are native; let them run, then re-read the toolbar state.
    if (['b', 'i', 'u', 'z', 'y'].includes(key)) {
      window.setTimeout(() => {
        emit();
        refreshState();
      }, 0);
    }
  };

  /**
   * Paste cleanup. Word, Google Docs and web pages carry a payload of
   * classes, inline styles, MSO conditional comments and nested spans; pasting
   * that raw is how a blog ends up with 11pt Calibri in the middle of an
   * article. cleanPastedHtml strips the source document's typography on top of
   * the usual allowlist; a plain-text paste is wrapped into paragraphs.
   */
  const handlePaste = (event) => {
    if (sourceMode) return;
    event.preventDefault();

    const html = event.clipboardData.getData('text/html');
    const text = event.clipboardData.getData('text/plain');

    if (html) {
      cmd.insertHTML(cleanPastedHtml(html));
    } else if (text) {
      const paragraphs = text
        .split(/\n{2,}/)
        .map((block) => `<p>${cmd.escapeText(block).replace(/\n/g, '<br>')}</p>`)
        .join('');
      cmd.insertHTML(paragraphs);
    }

    emit();
    refreshState();
  };

  /** Dropped content is pasted content by another route. */
  const handleDrop = (event) => {
    const html = event.dataTransfer?.getData('text/html');
    const text = event.dataTransfer?.getData('text/plain');
    if (!html && !text) return;
    event.preventDefault();
    cmd.insertHTML(html ? cleanPastedHtml(html) : `<p>${cmd.escapeText(text)}</p>`);
    emit();
  };

  // ── Render ─────────────────────────────────────────────────────────────

  const words = countWords(sourceMode ? sourceText : value);
  const characters = (sourceMode ? sourceText : value).replace(/<[^>]*>/g, '').length;

  return (
    <div
      ref={containerRef}
      className={`rich-editor overflow-hidden rounded-2xl border border-ash-200 bg-white shadow-soft ${
        fullscreen ? 'rich-editor--fullscreen' : ''
      }`}
    >
      <EditorToolbar state={state} onAction={handleAction} sourceMode={sourceMode} fullscreen={fullscreen} />

      {sourceMode ? (
        <textarea
          value={sourceText}
          onChange={(event) => setSourceText(event.target.value)}
          spellCheck={false}
          aria-label="HTML source"
          className="block w-full resize-none border-0 bg-ash-900 p-5 font-mono text-[13px] leading-[1.7] text-ash-100 focus:outline-none"
          style={{ minHeight, height: fullscreen ? 'calc(100vh - 132px)' : minHeight }}
        />
      ) : (
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-label="Article body"
          data-placeholder={placeholder}
          onInput={emit}
          onBlur={(event) => {
            // Clicking a toolbar dropdown blurs the editor without the author
            // leaving it. Rewriting the DOM here would destroy the selection
            // that the command is about to act on, so tidy up only when focus
            // genuinely leaves the editor.
            if (containerRef.current?.contains(event.relatedTarget)) return;

            // Tidy once the author stops typing, never mid-keystroke: this
            // rewrites the DOM and would otherwise move the caret.
            const node = editorRef.current;
            if (!node) return;
            const html = normalizeRichText(node.innerHTML);
            if (html !== node.innerHTML) node.innerHTML = html || EMPTY;
            syncEmptyState(node);
            emitted.current = html;
            onChange?.(html);
          }}
          onKeyDown={handleKeyDown}
          onKeyUp={refreshState}
          onMouseUp={refreshState}
          onPaste={handlePaste}
          onDrop={handleDrop}
          className="blog-prose rich-editor__surface p-6 focus:outline-none"
          style={{ minHeight, height: fullscreen ? 'calc(100vh - 132px)' : undefined }}
        />
      )}

      <div className="flex items-center justify-between border-t border-ash-200 bg-ash-50/80 px-4 py-2 font-ui text-[11.5px] text-ash-500">
        <span>{sourceMode ? 'Editing HTML source' : 'Rich text'}</span>
        <span>
          {words} {words === 1 ? 'word' : 'words'} · {characters} characters
        </span>
      </div>

      {dialog === 'link' && (
        <EditorDialog
          title="Insert link"
          icon="link"
          onClose={closeDialog}
          submitLabel="Apply"
          onSubmit={() => {
            setDialog(null);
            withSelection(() => {
              if (cmd.closestWithin(editorRef.current, 'a')) cmd.removeLink();
              cmd.insertLink(form);
            });
          }}
        >
          <DialogField label="URL" hint="example.com becomes https://example.com. javascript: links are refused.">
            <input
              type="text"
              value={form.url}
              onChange={(event) => setForm({ ...form, url: event.target.value })}
              placeholder="https://"
              className={dialogInputClass}
            />
          </DialogField>
          <DialogField label="Text to display">
            <input
              type="text"
              value={form.text}
              onChange={(event) => setForm({ ...form, text: event.target.value })}
              placeholder="Link text"
              className={dialogInputClass}
            />
          </DialogField>
          <label className="flex items-center gap-2.5">
            <input
              type="checkbox"
              checked={form.newTab}
              onChange={(event) => setForm({ ...form, newTab: event.target.checked })}
              className="h-4 w-4 rounded border-ash-300 text-brand-600"
            />
            <span className="font-ui text-[13px] text-ash-700">Open in a new tab</span>
          </label>
        </EditorDialog>
      )}

      {dialog === 'image' && (
        <EditorDialog
          title="Insert image"
          icon="image"
          onClose={closeDialog}
          onSubmit={() => {
            setDialog(null);
            withSelection(() => cmd.insertImage(form));
          }}
        >
          <DialogField label="Image URL">
            <input
              type="text"
              value={form.src}
              onChange={(event) => setForm({ ...form, src: event.target.value })}
              placeholder="https://"
              className={dialogInputClass}
            />
          </DialogField>
          <DialogField label="Alt text" hint="What the image shows, for screen readers and when it fails to load.">
            <input
              type="text"
              value={form.alt}
              onChange={(event) => setForm({ ...form, alt: event.target.value })}
              className={dialogInputClass}
            />
          </DialogField>
          <DialogField label="Caption (optional)">
            <input
              type="text"
              value={form.caption}
              onChange={(event) => setForm({ ...form, caption: event.target.value })}
              className={dialogInputClass}
            />
          </DialogField>
        </EditorDialog>
      )}

      {dialog === 'table' && (
        <EditorDialog
          title="Insert table"
          icon="table"
          onClose={closeDialog}
          onSubmit={() => {
            setDialog(null);
            withSelection(() =>
              cmd.insertTable({
                rows: Math.min(Math.max(Number(form.rows) || 1, 1), 50),
                columns: Math.min(Math.max(Number(form.columns) || 1, 1), 10),
                header: form.header,
              })
            );
          }}
        >
          <div className="flex gap-3">
            <DialogField label="Rows">
              <input
                type="number"
                min="1"
                max="50"
                value={form.rows}
                onChange={(event) => setForm({ ...form, rows: event.target.value })}
                className={dialogInputClass}
              />
            </DialogField>
            <DialogField label="Columns">
              <input
                type="number"
                min="1"
                max="10"
                value={form.columns}
                onChange={(event) => setForm({ ...form, columns: event.target.value })}
                className={dialogInputClass}
              />
            </DialogField>
          </div>
          <label className="flex items-center gap-2.5">
            <input
              type="checkbox"
              checked={form.header}
              onChange={(event) => setForm({ ...form, header: event.target.checked })}
              className="h-4 w-4 rounded border-ash-300 text-brand-600"
            />
            <span className="font-ui text-[13px] text-ash-700">First row is a header</span>
          </label>
        </EditorDialog>
      )}
    </div>
  );
};

export default RichTextEditor;
