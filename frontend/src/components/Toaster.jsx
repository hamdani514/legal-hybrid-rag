import { useEffect, useRef, useState } from 'react';
import { flushPendingToast, subscribeToasts } from '../lib/toast';

/**
 * Renders toast notifications (lib/toast.js) in the top-right corner: a white
 * card with a green tick for success or a red cross for an error. Each closes
 * by itself after its duration (paused while the pointer is over it) or when
 * clicked. Mounted once, in App.jsx, above the routes.
 */

const ICON = {
  success: { bg: 'bg-[#22c55e]', path: 'M5 10.5l3.2 3.2L15 7' },
  error: { bg: 'bg-[#ef4444]', path: 'M6.5 6.5l7 7M13.5 6.5l-7 7' },
};

const ToastCard = ({ item, onClose }) => {
  const [leaving, setLeaving] = useState(false);
  const timer = useRef(null);
  const remaining = useRef(item.duration);
  const startedAt = useRef(0);

  const close = () => {
    setLeaving(true);
    setTimeout(() => onClose(item.id), 180);
  };

  const start = () => {
    startedAt.current = Date.now();
    timer.current = setTimeout(close, remaining.current);
  };
  const pause = () => {
    clearTimeout(timer.current);
    remaining.current = Math.max(800, remaining.current - (Date.now() - startedAt.current));
  };

  useEffect(() => {
    start();
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const icon = ICON[item.type] || ICON.success;
  return (
    <div
      role={item.type === 'error' ? 'alert' : 'status'}
      onClick={close}
      onMouseEnter={pause}
      onMouseLeave={start}
      className={`pointer-events-auto flex w-full max-w-[26rem] cursor-pointer items-start gap-3 rounded-2xl bg-white px-4 py-3.5 shadow-[0_10px_30px_-8px_rgba(15,23,42,0.22),0_2px_8px_-2px_rgba(15,23,42,0.08)] ring-1 ring-black/[0.04] ${
        leaving ? 'animate-[toastOut_0.18s_ease-in_forwards]' : 'animate-[toastIn_0.25s_ease-out]'
      }`}
    >
      <span className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full ${icon.bg}`}>
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d={icon.path} />
        </svg>
      </span>
      <p className="font-ui text-[14px] leading-[1.45] text-[#1f2937]">{item.message}</p>
    </div>
  );
};

const Toaster = () => {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const unsubscribe = subscribeToasts((item) =>
      // Newest on top; at most five on screen.
      setItems((prev) => [item, ...prev].slice(0, 5))
    );
    flushPendingToast();   // one left by toast.afterReload before a full page load
    return unsubscribe;
  }, []);

  const remove = (id) => setItems((prev) => prev.filter((t) => t.id !== id));

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 top-4 z-[1000] flex w-[calc(100%-2rem)] max-w-[26rem] flex-col items-end gap-2.5 sm:right-6 sm:top-5"
    >
      <style>{`
        @keyframes toastIn { from { opacity: 0; transform: translateY(-8px) scale(0.98); } to { opacity: 1; transform: none; } }
        @keyframes toastOut { to { opacity: 0; transform: translateX(16px); } }
      `}</style>
      {items.map((item) => (
        <ToastCard key={item.id} item={item} onClose={remove} />
      ))}
    </div>
  );
};

export default Toaster;
