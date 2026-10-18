import { useEffect, useRef } from 'react';

/**
 * The shell every editor dialog uses: a centred panel, a backdrop, Escape to
 * close, focus moved in on open and returned to the editor on close.
 *
 * Dialogs must not steal the selection they are about to act on, so the
 * caller saves the range before opening and restores it on submit — see
 * saveRange/restoreRange in editorCommands.js.
 */
const EditorDialog = ({ title, icon = 'tune', onClose, onSubmit, submitLabel = 'Insert', children }) => {
  const panelRef = useRef(null);

  useEffect(() => {
    const field = panelRef.current?.querySelector('input, textarea, select');
    field?.focus();

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-ink-900/40 px-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-md rounded-2xl border border-ash-200 bg-white p-6 shadow-card-lg"
      >
        <div className="flex items-center gap-2.5">
          <span aria-hidden="true" className="material-symbols-outlined text-[20px] text-brand-600">
            {icon}
          </span>
          <h2 className="font-display text-[17px] font-bold text-ash-900">{title}</h2>
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          {children}

          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-ash-300 bg-white px-4 py-2.5 font-ui text-[13.5px] font-semibold text-ash-700 transition-colors hover:bg-ash-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="grad-btn rounded-xl px-5 py-2.5 font-ui text-[13.5px] font-bold text-white shadow-glow"
            >
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export const DialogField = ({ label, hint, children }) => (
  <label className="block">
    <span className="mb-1.5 block font-ui text-[12.5px] font-semibold text-ash-700">{label}</span>
    {children}
    {hint && <span className="mt-1 block font-prose text-[11.5px] text-ash-500">{hint}</span>}
  </label>
);

export const dialogInputClass =
  'w-full rounded-xl border border-ash-300 bg-white px-3.5 py-2.5 font-prose text-[14px] text-ash-900 transition-colors focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100';

export default EditorDialog;
