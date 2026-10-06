import { useEffect, useRef, useState } from 'react';

/**
 * Copy some text to the clipboard, with the result shown on the button.
 *
 * Why not just navigator.clipboard: that API only exists in a secure context
 * (HTTPS, or localhost). This app is opened over the LAN by its IP
 * (http://192.168.x.x:5173), where `navigator.clipboard` is undefined, so a
 * plain implementation would silently do nothing on exactly the machines the
 * owner demonstrates it on. The old execCommand path is kept as the fallback,
 * and the button reports honestly when both are unavailable.
 */

const copyText = async (text) => {
  if (!text) return false;
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the textarea path */
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    // Off-screen but still selectable; readOnly stops the mobile keyboard.
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, area.value.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
};

const CopyButton = ({ text, label = 'Copy', copiedLabel = 'Copied', title, className = '', compact = false }) => {
  const [state, setState] = useState('idle'); // idle | done | failed
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const onClick = async () => {
    const value = typeof text === 'function' ? text() : text;
    const ok = await copyText(value);
    setState(ok ? 'done' : 'failed');
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState('idle'), 1800);
  };

  const icon = state === 'done' ? 'check' : state === 'failed' ? 'error' : 'content_copy';
  const text_ = state === 'done' ? copiedLabel : state === 'failed' ? 'Press Ctrl+C' : label;
  const tone =
    state === 'done'
      ? 'text-green-700'
      : state === 'failed'
        ? 'text-amber-700'
        : 'text-ash-500 hover:text-brand-700';

  return (
    <button
      type="button"
      onClick={onClick}
      title={title || 'Copy to clipboard'}
      aria-label={title || 'Copy to clipboard'}
      className={`inline-flex items-center gap-1 rounded-lg font-ui text-[12px] font-semibold transition-colors ${
        compact ? 'px-1.5 py-1' : 'px-2 py-1 hover:bg-ash-100'
      } ${tone} ${className}`}
    >
      <span className="material-symbols-outlined text-[16px]">{icon}</span>
      {!compact && <span>{text_}</span>}
    </button>
  );
};

export default CopyButton;
