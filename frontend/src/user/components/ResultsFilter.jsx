import { useState } from 'react';
import { caseJudges, prettyOutcome } from '../lib/answerFormat';
import { EMPTY_FILTERS, matchesFilters, OUTCOMES } from '../lib/filters';

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
 * The filter dialog (its matching rules are in ../lib/filters.js). Edits a local draft so nothing changes behind the reader
 * until Apply is pressed; Reset removes every filter at once and closes.
 */
const FilterDialog = ({ cases = [], filters, onApply, onClose, Modal, searchesAll = false, beforeSearch = false }) => {
  const [draft, setDraft] = useState(filters);
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  const uniq = (v) => [...new Set(v.filter(Boolean))].sort();
  // Filtering covers every case found, so offer every decision, not only
  // those among the cases on screen.
  const outcomes = searchesAll || beforeSearch
    ? OUTCOMES
    : uniq(cases.map((c) => c.card?.outcome)).filter((o) => o !== 'unknown');
  const judges = uniq(cases.flatMap((c) => caseJudges(c.card)));

  const preview = cases.filter((c) => matchesFilters(c, draft)).length;

  return (
    <Modal
      title="Filter results"
      subtitle="Every field is optional — leave one blank and it will not narrow anything. A case whose decision, date or judges could not be read from the judgment is left out when you filter on that field."
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

        <Field label="Case number or party" hint="Spacing and dots do not matter: C.P.L.A. 3031 2021 and CPLA 3031/2021 both work.">
          <input type="search" value={draft.query} placeholder="e.g. C.P.L.A. 3031 2021, or Federation of Pakistan"
                 onChange={(e) => set('query', e.target.value)} className={inputCls} />
        </Field>

        <Field label="Judge name" hint="Part of the name is enough; titles like Justice or CJ are optional.">
          <input type="search" list="filter-judges" value={draft.judge} placeholder="e.g. Justice Munib Akhtar"
                 onChange={(e) => set('judge', e.target.value)} className={inputCls} />
          <datalist id="filter-judges">
            {judges.map((j) => <option key={j} value={j} />)}
          </datalist>
        </Field>

        <div className="flex flex-wrap items-center gap-3 border-t border-ash-200 pt-4">
          <span className="max-w-[18rem] font-prose text-[12.5px] leading-snug text-ash-600">
            {beforeSearch ? (
              <>
                <span aria-hidden="true" className="material-symbols-outlined mr-1 align-[-3px] text-[15px] text-brand-500">
                  travel_explore
                </span>
                Applied to the results of your next search. You can change or reset it afterwards without using another search.
              </>
            ) : searchesAll ? (
              <>
                <span aria-hidden="true" className="material-symbols-outlined mr-1 align-[-3px] text-[15px] text-brand-500">
                  travel_explore
                </span>
                Applies to every case found for this search — not only the {cases.length} on screen.
              </>
            ) : (
              `${preview} of ${cases.length} judgment${cases.length === 1 ? '' : 's'} match`
            )}
          </span>
          <span className="ml-auto flex items-center gap-2">
            <button type="button" onClick={() => { onApply({ ...EMPTY_FILTERS }); onClose(); }}
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
