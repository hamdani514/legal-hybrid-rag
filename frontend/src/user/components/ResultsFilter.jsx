import { useState } from 'react';
import { caseJudges, prettyOutcome } from '../lib/answerFormat';

/*
 * Narrowing a multi-case result: by final decision, a date range, case number
 * and judge.
 *
 * Every field is optional and they combine with AND, so leaving one empty
 * simply does not constrain that dimension. The work happens on data already
 * on screen - no request, no AI call.
 */

export const EMPTY_FILTERS = { outcome: '', judge: '', from: '', to: '', query: '' };

/** How many fields are actually constraining the list (for the button badge). */
export const activeFilterCount = (f) =>
  ['outcome', 'judge', 'from', 'to', 'query'].filter((k) => (f?.[k] || '').trim()).length;

/**
 * A judgment's decision date as a Date, or null.
 *
 * Case cards carry "28.12.2021" (DD.MM.YYYY), which `new Date()` misreads as
 * a US month/day string, so it is parsed explicitly. ISO dates are accepted
 * too, because that is what the date inputs produce.
 */
export const caseDate = (card) => {
  const raw = String(card?.decision_date || '').trim();
  let m = /^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$/.exec(raw);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return null;
};

/** Does one result match the active filters? Empty fields never exclude. */
export const matchesFilters = (cite, f) => {
  const card = cite.card || {};

  if (f.outcome && String(card.outcome || '') !== f.outcome) return false;

  if (f.judge?.trim()) {
    const needle = f.judge.trim().toLowerCase();
    if (!caseJudges(card).some((j) => j.toLowerCase().includes(needle))) return false;
  }

  if (f.from || f.to) {
    const when = caseDate(card);
    // A judgment with no usable date cannot be shown to fall inside a range.
    if (!when) return false;
    if (f.from && when < new Date(`${f.from}T00:00:00`)) return false;
    if (f.to && when > new Date(`${f.to}T23:59:59`)) return false;
  }

  if (f.query?.trim()) {
    const needle = f.query.trim().toLowerCase();
    const hay = [card.case_display, cite.filename, cite.judgment_id, card.appellant,
                 card.respondent, card.subject]
      .filter(Boolean).join(' ').toLowerCase();
    if (!hay.includes(needle)) return false;
  }
  return true;
};

const Field = ({ label, hint, children }) => (
  <label className="flex flex-col gap-1.5">
    <span className="font-ui text-[11px] font-bold uppercase tracking-wider text-ash-600">
      {label}
    </span>
    {children}
    {hint && <span className="font-prose text-[11px] text-ash-400">{hint}</span>}
  </label>
);

const inputCls =
  'w-full rounded-lg border border-ash-200 bg-white px-3 py-2 font-prose text-[13px] text-ash-900 outline-none transition-colors focus:border-brand-400 focus:ring-2 focus:ring-brand-100';

/**
 * The filter dialog. Edits a local draft so nothing changes behind the reader
 * until Apply is pressed; Reset clears every field at once.
 */
const FilterDialog = ({ cases, filters, onApply, onClose, Modal }) => {
  const [draft, setDraft] = useState(filters);
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  const uniq = (v) => [...new Set(v.filter(Boolean))].sort();
  const outcomes = uniq(cases.map((c) => c.card?.outcome));
  const judges = uniq(cases.flatMap((c) => caseJudges(c.card)));

  const preview = cases.filter((c) => matchesFilters(c, draft)).length;

  return (
    <Modal
      title="Filter results"
      subtitle="Every field is optional — leave one blank and it will not narrow anything."
      onClose={onClose}
    >
      <div className="flex flex-col gap-5">
        <Field label="Final decision">
          <select value={draft.outcome} onChange={(e) => set('outcome', e.target.value)} className={inputCls}>
            <option value="">Any decision</option>
            {outcomes.map((o) => (
              <option key={o} value={o}>{prettyOutcome(o)}</option>
            ))}
          </select>
        </Field>

        <div>
          <span className="font-ui text-[11px] font-bold uppercase tracking-wider text-ash-600">
            Decided between
          </span>
          <div className="mt-1.5 flex items-center gap-3">
            <input type="date" value={draft.from} max={draft.to || undefined}
                   onChange={(e) => set('from', e.target.value)} className={inputCls} aria-label="From date" />
            <span className="font-prose text-[13px] text-ash-500">to</span>
            <input type="date" value={draft.to} min={draft.from || undefined}
                   onChange={(e) => set('to', e.target.value)} className={inputCls} aria-label="To date" />
          </div>
          <span className="mt-1.5 block font-prose text-[11px] text-ash-400">
            Leave both blank for any date, or set just one for "before" / "after".
          </span>
        </div>

        <Field label="Case number or party" hint="Matches part of a case number, a filename or a party name.">
          <input type="search" value={draft.query} placeholder="e.g. 26-K, or Federation of Pakistan"
                 onChange={(e) => set('query', e.target.value)} className={inputCls} />
        </Field>

        <Field label="Judge" hint="Part of a name is enough.">
          <input type="search" list="filter-judges" value={draft.judge} placeholder="e.g. Munib Akhtar"
                 onChange={(e) => set('judge', e.target.value)} className={inputCls} />
          <datalist id="filter-judges">
            {judges.map((j) => <option key={j} value={j} />)}
          </datalist>
        </Field>

        <div className="flex flex-wrap items-center gap-3 border-t border-ash-200 pt-4">
          <span className="font-prose text-[13px] text-ash-600">
            {preview} of {cases.length} judgment{cases.length === 1 ? '' : 's'} match
          </span>
          <span className="ml-auto flex items-center gap-2">
            <button type="button" onClick={() => setDraft({ ...EMPTY_FILTERS })}
                    className="rounded-full border border-ash-300 bg-white px-4 py-2 font-ui text-[13px] font-semibold text-ash-700 transition-colors hover:border-brand-300 hover:text-brand-700">
              Reset
            </button>
            <button type="button" onClick={() => { onApply(draft); onClose(); }}
                    className="grad-btn rounded-full px-5 py-2 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:-translate-y-0.5">
              Apply
            </button>
          </span>
        </div>
      </div>
    </Modal>
  );
};

export default FilterDialog;
