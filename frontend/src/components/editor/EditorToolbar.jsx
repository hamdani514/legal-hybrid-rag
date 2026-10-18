import { useEffect, useRef, useState } from 'react';

/**
 * The toolbar. It is presentational: every button reports an action name and
 * an optional value to the editor, which owns the commands and the state.
 *
 * Buttons use onMouseDown with preventDefault rather than onClick, because a
 * click moves focus out of the editable area first and collapses the selection
 * the command is meant to act on.
 */

const BLOCK_OPTIONS = [
  { value: 'p', label: 'Paragraph' },
  { value: 'h2', label: 'Heading 2' },
  { value: 'h3', label: 'Heading 3' },
  { value: 'h4', label: 'Heading 4' },
  { value: 'blockquote', label: 'Quote' },
  { value: 'pre', label: 'Code block' },
];

const FONT_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'Outfit, system-ui, sans-serif', label: 'Outfit' },
  { value: 'Lato, system-ui, sans-serif', label: 'Lato' },
  { value: 'Georgia, serif', label: 'Georgia' },
  { value: '"Times New Roman", serif', label: 'Times' },
  { value: 'Arial, sans-serif', label: 'Arial' },
  { value: 'ui-monospace, SFMono-Regular, monospace', label: 'Monospace' },
];

const SIZE_OPTIONS = ['13px', '15px', '17px', '19px', '22px', '26px', '32px'];

// Drawn from the site's own tokens, so an author cannot pick a colour that
// clashes with the article page. The last row is greys for de-emphasis.
const TEXT_COLORS = [
  '#111827', '#374151', '#6b7280', '#9ca3af',
  '#0065c7', '#0085ff', '#00a3ff', '#2400ff',
  '#a97c24', '#d3a44d', '#b91c1c', '#15803d',
];

const HIGHLIGHT_COLORS = [
  'transparent', '#fef3c7', '#dcfce7', '#dbeafe',
  '#fee2e2', '#f3e8ff', '#e0f0ff', '#f1f5f9',
];

const Divider = () => <span aria-hidden="true" className="mx-1 h-6 w-px shrink-0 bg-ash-200" />;

const Button = ({ icon, label, active, disabled, onAction, children }) => (
  <button
    type="button"
    title={label}
    aria-label={label}
    aria-pressed={active === undefined ? undefined : active}
    disabled={disabled}
    // See the note at the top: mousedown, not click.
    onMouseDown={(event) => {
      event.preventDefault();
      if (!disabled) onAction();
    }}
    className={`flex h-8 min-w-8 shrink-0 items-center justify-center gap-1 rounded-lg px-1.5 font-ui text-[12.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
      active
        ? 'bg-brand-100 text-brand-700'
        : 'text-ash-600 hover:bg-ash-100 hover:text-ash-900'
    }`}
  >
    {icon && (
      <span aria-hidden="true" className="material-symbols-outlined text-[19px]">
        {icon}
      </span>
    )}
    {children}
  </button>
);

/** A swatch grid that closes when you click away from it. */
const ColorMenu = ({ label, icon, colors, accent, onPick }) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div ref={wrapperRef} className="relative shrink-0">
      <button
        type="button"
        title={label}
        aria-label={label}
        aria-expanded={open}
        onMouseDown={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
        className="flex h-8 items-center gap-0.5 rounded-lg px-1.5 text-ash-600 transition-colors hover:bg-ash-100 hover:text-ash-900"
      >
        <span className="relative flex flex-col items-center">
          <span aria-hidden="true" className="material-symbols-outlined text-[19px] leading-none">
            {icon}
          </span>
          <span
            aria-hidden="true"
            className="mt-0.5 h-[3px] w-[18px] rounded-full"
            style={{ background: accent }}
          />
        </span>
        <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
          arrow_drop_down
        </span>
      </button>

      {open && (
        <div className="absolute left-0 top-10 z-30 w-[188px] rounded-xl border border-ash-200 bg-white p-2.5 shadow-card">
          <div className="grid grid-cols-4 gap-1.5">
            {colors.map((color) => (
              <button
                key={color}
                type="button"
                title={color === 'transparent' ? 'None' : color}
                aria-label={color === 'transparent' ? 'No highlight' : color}
                onMouseDown={(event) => {
                  event.preventDefault();
                  onPick(color);
                  setOpen(false);
                }}
                className="h-7 w-7 rounded-md border border-ash-200 transition-transform hover:scale-110"
                style={
                  color === 'transparent'
                    ? { backgroundImage: 'linear-gradient(45deg,#fff 45%,#ef4444 45%,#ef4444 55%,#fff 55%)' }
                    : { background: color }
                }
              />
            ))}
          </div>
          <label className="mt-2.5 flex items-center gap-2 border-t border-ash-150 pt-2.5">
            <span className="font-ui text-[11.5px] font-semibold text-ash-600">Custom</span>
            <input
              type="color"
              onChange={(event) => {
                onPick(event.target.value);
                setOpen(false);
              }}
              className="h-7 w-10 cursor-pointer rounded border border-ash-200 bg-white"
            />
          </label>
        </div>
      )}
    </div>
  );
};

const selectClass =
  'h-8 shrink-0 rounded-lg border border-ash-200 bg-white px-2 font-ui text-[12.5px] text-ash-700 transition-colors hover:border-ash-300 focus:border-brand-400 focus:outline-none';

const EditorToolbar = ({ state, onAction, sourceMode, fullscreen }) => {
  const act = (action, value) => onAction(action, value);

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-ash-200 bg-ash-50/80 px-2.5 py-2">
      <select
        value={state.block}
        disabled={sourceMode}
        title="Paragraph format"
        aria-label="Paragraph format"
        onChange={(event) => act('block', event.target.value)}
        className={`${selectClass} w-[118px]`}
      >
        {BLOCK_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <select
        defaultValue=""
        disabled={sourceMode}
        title="Font"
        aria-label="Font"
        onChange={(event) => act('font', event.target.value)}
        className={`${selectClass} w-[104px]`}
      >
        {FONT_OPTIONS.map((option) => (
          <option key={option.label} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <select
        defaultValue=""
        disabled={sourceMode}
        title="Font size"
        aria-label="Font size"
        onChange={(event) => act('size', event.target.value)}
        className={`${selectClass} w-[76px]`}
      >
        <option value="">Size</option>
        {SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>

      <Divider />

      <Button icon="format_bold" label="Bold (Ctrl+B)" active={state.bold} disabled={sourceMode} onAction={() => act('bold')} />
      <Button icon="format_italic" label="Italic (Ctrl+I)" active={state.italic} disabled={sourceMode} onAction={() => act('italic')} />
      <Button icon="format_underlined" label="Underline (Ctrl+U)" active={state.underline} disabled={sourceMode} onAction={() => act('underline')} />
      <Button icon="strikethrough_s" label="Strikethrough" active={state.strike} disabled={sourceMode} onAction={() => act('strike')} />
      <Button icon="superscript" label="Superscript" active={state.superscript} disabled={sourceMode} onAction={() => act('superscript')} />
      <Button icon="subscript" label="Subscript" active={state.subscript} disabled={sourceMode} onAction={() => act('subscript')} />

      {!sourceMode && (
        <>
          <ColorMenu label="Text colour" icon="format_color_text" accent="#0085ff" colors={TEXT_COLORS} onPick={(color) => act('color', color)} />
          <ColorMenu label="Highlight" icon="format_ink_highlighter" accent="#fef3c7" colors={HIGHLIGHT_COLORS} onPick={(color) => act('highlight', color)} />
        </>
      )}

      <Divider />

      <Button icon="format_list_bulleted" label="Bulleted list" active={state.bulleted} disabled={sourceMode} onAction={() => act('bulleted')} />
      <Button icon="format_list_numbered" label="Numbered list" active={state.numbered} disabled={sourceMode} onAction={() => act('numbered')} />
      <Button icon="format_indent_increase" label="Indent" disabled={sourceMode} onAction={() => act('indent')} />
      <Button icon="format_indent_decrease" label="Outdent" disabled={sourceMode} onAction={() => act('outdent')} />

      <Divider />

      <Button icon="format_align_left" label="Align left" active={state.alignLeft} disabled={sourceMode} onAction={() => act('align', 'left')} />
      <Button icon="format_align_center" label="Align centre" active={state.alignCenter} disabled={sourceMode} onAction={() => act('align', 'center')} />
      <Button icon="format_align_right" label="Align right" active={state.alignRight} disabled={sourceMode} onAction={() => act('align', 'right')} />
      <Button icon="format_align_justify" label="Justify" active={state.alignJustify} disabled={sourceMode} onAction={() => act('align', 'justify')} />

      <Divider />

      <Button icon="link" label="Insert link (Ctrl+K)" active={state.link} disabled={sourceMode} onAction={() => act('link')} />
      <Button icon="link_off" label="Remove link" disabled={sourceMode || !state.link} onAction={() => act('unlink')} />
      <Button icon="image" label="Insert image" disabled={sourceMode} onAction={() => act('image')} />
      <Button icon="table" label="Insert table" disabled={sourceMode} onAction={() => act('table')} />
      <Button icon="horizontal_rule" label="Horizontal rule" disabled={sourceMode} onAction={() => act('rule')} />
      <Button icon="format_quote" label="Quote" active={state.block === 'blockquote'} disabled={sourceMode} onAction={() => act('block', state.block === 'blockquote' ? 'p' : 'blockquote')} />

      <Divider />

      <Button icon="format_clear" label="Clear formatting" disabled={sourceMode} onAction={() => act('clear')} />
      <Button icon="undo" label="Undo (Ctrl+Z)" disabled={sourceMode} onAction={() => act('undo')} />
      <Button icon="redo" label="Redo (Ctrl+Shift+Z)" disabled={sourceMode} onAction={() => act('redo')} />

      <div className="ml-auto flex items-center gap-0.5">
        <Button icon="code" label="Edit HTML source" active={sourceMode} onAction={() => act('source')} />
        <Button
          icon={fullscreen ? 'close_fullscreen' : 'open_in_full'}
          label={fullscreen ? 'Exit full screen' : 'Full screen'}
          active={fullscreen}
          onAction={() => act('fullscreen')}
        />
      </div>
    </div>
  );
};

export default EditorToolbar;
