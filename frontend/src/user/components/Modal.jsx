import { useEffect } from 'react';

/** A dialog. Closes on the backdrop, on Escape and on the explicit control. */
const Modal = ({ title, subtitle, onClose, children, wide = false }) => {
  useEffect(() => {
    // On the window: focus may still be on the button that opened the dialog.
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ash-900/45 p-0 backdrop-blur-sm sm:items-center sm:p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-3xl bg-white shadow-card-lg sm:rounded-3xl ${
          wide ? 'sm:max-w-5xl' : 'sm:max-w-2xl'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-ash-200 px-6 py-5">
          <div>
            <h2 className="font-display text-lg font-bold text-ash-900">{title}</h2>
            {subtitle && <p className="mt-1 font-prose text-xs text-ash-500">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-ash-500 transition-colors hover:bg-ash-100 hover:text-ash-900"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>
        <div className="flex-1 overflow-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
};

export default Modal;
