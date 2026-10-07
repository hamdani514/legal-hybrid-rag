import { useCallback, useEffect, useState } from 'react';
import apiFetch, { TOKEN_KEY } from '../../lib/api';
import CopyButton from './CopyButton';
import FilterDialog, { EMPTY_FILTERS, activeFilterCount, matchesFilters } from './ResultsFilter';
import {
  ANSWER_STATUS,
  answerStatusOf,
  caseSummaryLines,
  fitSection,
  isEmptyAnswer,
  judgmentShareText,
  meaningfulSections,
  prettyCaseName,
  prettyOutcome,
  prettySections,
  responseShareText,
} from '../lib/answerFormat';

/**
 * Everything the workspace shows after a search.
 *
 * The rendering follows what was actually retrieved, because the previous
 * behaviour — always three authorities, always three download buttons, always
 * an answer — was telling researchers things that were not true. A query with
 * no answer in the archive came back with three judgments at "Relevance 100%"
 * and a final decision lifted from an unrelated case.
 *
 *   nothing retrieved -> the explanation alone. No list, no downloads, no
 *                        answer, nothing that implies an authority exists.
 *   one judgment      -> that judgment, discussed, with its own download.
 *   several           -> each discussed in turn, then the actions: see every
 *                        judgment in one place, or compare them as a table.
 *
 * The backend applies a relevance floor, so a judgment reaching this component
 * has already been found genuinely responsive. The component's job is to not
 * overstate what arrived.
 *
 * Analyses are rendered by `answer_status`, never by inspecting the text:
 *   ready        -> the analysis, plus how it fits the user's situation.
 *   on_demand    -> the case card and an "Analyse this case" button. The shared
 *                   LLM budget is small, so only the top result is analysed
 *                   with the search.
 *   rate_limited -> "busy, retrying" with automatic and manual retry.
 *   error        -> a plain message and a retry button.
 */

// How a rate-limited analysis retries by itself before leaving it to the user.
const AUTO_RETRY_DELAY_MS = 20000;
const MAX_AUTO_RETRIES = 3;

/** A link cannot send an Authorization header, so the token rides in the URL. */
const withToken = (url) => {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return url;
    return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
  } catch {
    return url;
  }
};

/** The `detail` of an error response, when it is a plain string. */
const errorDetail = async (res) => {
  try {
    const body = await res.json();
    return typeof body?.detail === 'string' ? body.detail : '';
  } catch {
    return '';
  }
};

const DownloadButton = ({ cite, block = false }) => (
  <a
    href={withToken(cite.download_url || `/api/admin/judgments/${cite.judgment_id}/download`)}
    target="_blank"
    rel="noopener noreferrer"
    download={cite.filename || 'judgment.pdf'}
    className={`inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#261900] px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition-all hover:-translate-y-0.5 hover:bg-brand-600 hover:shadow-md ${
      block ? 'w-full sm:w-auto' : ''
    }`}
    title={`Download ${cite.filename}`}
  >
    <span className="material-symbols-outlined text-[15px]">download</span>
    <span>Download PDF</span>
  </a>
);

// The v2 pipeline orders results by fusion and scores them with the
// cross-encoder, so raw percentages are not monotonic down the list — a case
// ranked first could show 19% above one showing 82%, which reads as a broken
// ranking. v2 therefore sends a coarse label the reader can act on; v1 results
// carry no label and keep the percentage.
const CONFIDENCE = {
  high: { label: 'Strong match', cls: 'bg-mint-400/15 text-mint-700' },
  medium: { label: 'Possible match — verify', cls: 'bg-amber-400/20 text-ash-800' },
  related: { label: 'Related case', cls: 'bg-ash-100 text-ash-600' },
};

const RelevanceBadge = ({ score, confidence }) => {
  const tier = CONFIDENCE[confidence];
  if (tier) {
    return (
      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${tier.cls}`}>
        {tier.label}
      </span>
    );
  }
  return (
    <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-semibold text-brand-800">
      Relevance {Math.round((score ?? 0) * 100)}%
    </span>
  );
};

const CiteRow = ({ cite }) => (
  <div className="flex flex-col justify-between gap-3 rounded-xl border border-ash-200 bg-ash-50/70 p-3 shadow-xs transition-all hover:border-brand-300 hover:bg-ash-50 sm:flex-row sm:items-center">
    <div className="flex min-w-0 items-start gap-2.5">
      <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
        <span className="material-symbols-outlined text-[18px]">picture_as_pdf</span>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium text-ash-900" title={cite.filename}>
            {cite.filename}
          </span>
          <RelevanceBadge score={cite.similarity_score} confidence={cite.confidence} />
        </div>
        {cite.sections_retrieved?.length > 0 && (
          <p className="mt-0.5 truncate text-xs text-ash-500">
            Sections: {prettySections(cite.sections_retrieved)}
          </p>
        )}
      </div>
    </div>
    <div className="flex-shrink-0 self-end sm:self-center">
      <DownloadButton cite={cite} />
    </div>
  </div>
);

/** A dialog. Closes on the backdrop, on Escape and on the explicit control. */
const Modal = ({ title, subtitle, onClose, children, wide = false }) => (
  <div
    className="fixed inset-0 z-50 flex items-end justify-center bg-ash-900/45 p-0 backdrop-blur-sm sm:items-center sm:p-6"
    onClick={onClose}
    onKeyDown={(e) => e.key === 'Escape' && onClose()}
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

const CompareTable = ({ table }) => (
  // The table is the one thing allowed to scroll sideways on a phone; every
  // other surface stays within the viewport.
  <div className="overflow-x-auto">
    <table className="w-full min-w-[42rem] border-collapse text-left">
      <thead>
        <tr>
          <th className="sticky left-0 z-10 bg-white px-3 py-2.5 font-display text-[11px] font-bold uppercase tracking-wider text-ash-500">
            Field
          </th>
          {table.rows.map((row) => (
            <th
              key={row.judgment_id}
              className="min-w-[15rem] border-b border-ash-200 px-3 py-2.5 font-display text-[12.5px] font-bold text-ash-900"
            >
              {prettyCaseName(row.filename, row.judgment_id.slice(0, 8))}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.fields.map((field, index) => (
          <tr key={field.key} className={index % 2 ? 'bg-ash-50/60' : ''}>
            <th
              scope="row"
              className={`sticky left-0 z-10 whitespace-nowrap px-3 py-3 align-top font-display text-[12px] font-semibold text-ash-600 ${
                index % 2 ? 'bg-ash-50/60' : 'bg-white'
              }`}
            >
              {field.label}
            </th>
            {table.rows.map((row) => (
              <td
                key={row.judgment_id + field.key}
                className="px-3 py-3 align-top font-prose text-[13px] leading-relaxed text-ash-700"
              >
                {row[field.key] || '—'}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const FIT_STYLE = {
  distinguishable: {
    cls: 'border-amber-400/40 bg-amber-400/10',
    icon: 'call_split',
    label: 'How it fits your situation — differences found',
  },
  matches: {
    cls: 'border-mint-400/40 bg-mint-400/10',
    icon: 'task_alt',
    label: 'How it fits your situation',
  },
  partial: {
    cls: 'border-brand-100 bg-brand-50',
    icon: 'compare',
    label: 'How it fits your situation',
  },
};

/** The model's check of the judgment against the user's own description. */
const FitCallout = ({ fit }) => {
  const style = FIT_STYLE[fit.verdict] || FIT_STYLE.partial;
  return (
    <div className={`mt-5 rounded-xl border px-4 py-3 ${style.cls}`}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[16px] text-ash-600">{style.icon}</span>
        <h4 className="font-display text-[11px] font-semibold uppercase tracking-wider text-ash-700">
          {style.label}
        </h4>
      </div>
      <p className="whitespace-pre-line font-prose text-sm leading-relaxed text-ash-900">{fit.body}</p>
    </div>
  );
};

/** What the case is, from its case card, for a result not analysed yet. */
const CardSummary = ({ card }) => {
  if (!card) return null;
  const outcome = prettyOutcome(card.outcome);
  const parties =
    card.appellant && card.respondent ? `${card.appellant} v. ${card.respondent}` : '';
  const summary = card.headnote || card.holding || '';
  return (
    <div className="mt-4 rounded-xl border border-ash-200 bg-ash-50/70 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        {card.case_display && (
          <span className="font-display text-[13px] font-semibold text-ash-900">
            {card.case_display}
          </span>
        )}
        {card.subject && (
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-semibold text-brand-800">
            {card.subject}
          </span>
        )}
        {outcome && (
          <span className="rounded-full bg-ash-100 px-2 py-0.5 text-[10px] font-semibold text-ash-700">
            {outcome}
          </span>
        )}
        {card.decision_date && (
          <span className="text-[11px] text-ash-500">Decided {card.decision_date}</span>
        )}
      </div>
      {parties && <p className="mt-1 font-prose text-xs text-ash-600">{parties}</p>}
      {summary && (
        <p className="mt-2 font-prose text-[13px] leading-relaxed text-ash-700">{summary}</p>
      )}
    </div>
  );
};

const AnalyseButton = ({ onClick, label, icon = 'auto_awesome', disabled = false }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className="grad-btn inline-flex items-center gap-1.5 rounded-full px-4 py-2 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:-translate-y-0.5 hover:shadow-glow-lg disabled:cursor-not-allowed disabled:opacity-60"
  >
    <span className="material-symbols-outlined text-[16px]">{icon}</span>
    {label}
  </button>
);

/**
 * One result's analysis and how it got there. Starts from what the search
 * returned; "Analyse this case" and every retry go through POST /query/answer,
 * which is cached server-side per (query, judgment).
 */
const useAnalysis = (cite, query) => {
  const [state, setState] = useState(() => ({
    status: answerStatusOf(cite),
    answer: cite.llm_answer || null,
    loading: false,
    notice: '',
    retries: 0,
  }));

  const analyse = useCallback(
    async ({ automatic = false } = {}) => {
      if (!query) return;
      setState((s) => ({ ...s, loading: true, retries: automatic ? s.retries + 1 : 0 }));
      try {
        const res = await apiFetch('/query/answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, judgment_id: cite.judgment_id }),
        });
        if (res.status === 429) {
          // A per-user limit, or the shared budget: busy either way. The
          // per-user message says when to come back, so it is shown as-is and
          // not retried automatically.
          const detail = await errorDetail(res);
          setState((s) => ({
            ...s,
            status: ANSWER_STATUS.RATE_LIMITED,
            loading: false,
            notice: detail,
            retries: detail ? MAX_AUTO_RETRIES : s.retries,
          }));
          return;
        }
        if (!res.ok) {
          setState((s) => ({ ...s, status: ANSWER_STATUS.ERROR, loading: false, notice: '' }));
          return;
        }
        const data = await res.json();
        setState((s) => ({
          ...s,
          status: data.answer_status || ANSWER_STATUS.ERROR,
          answer: data.answer || null,
          loading: false,
          notice: '',
        }));
      } catch (error) {
        console.error('Analysis request failed:', error);
        setState((s) => ({ ...s, status: ANSWER_STATUS.ERROR, loading: false, notice: '' }));
      }
    },
    [query, cite.judgment_id]
  );

  // A rate-limited analysis retries itself a few times, spaced out so the
  // shared per-minute window has room again.
  const waiting =
    state.status === ANSWER_STATUS.RATE_LIMITED &&
    !state.loading &&
    Boolean(query) &&
    state.retries < MAX_AUTO_RETRIES;
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setTimeout(() => analyse({ automatic: true }), AUTO_RETRY_DELAY_MS);
    return () => clearTimeout(timer);
  }, [waiting, analyse]);

  return { ...state, waiting, analyse };
};

/** One judgment: what it is, what it held, and how to read it in full. */
/**
 * The three-line summary: who the parties were, what the legal problem was,
 * and how it ended. Built from the case card, so it opens instantly and spends
 * no Gemini quota — it summarises facts already retrieved, not new analysis.
 */
const ThreeLineSummary = ({ lines }) => (
  <div className="mt-3 rounded-xl border border-brand-100 bg-brand-50/60 px-4 py-3">
    <ul className="flex flex-col gap-2">
      {lines.map((line) => (
        <li key={line.label} className="flex gap-2.5">
          <span className="w-[86px] shrink-0 pt-[1px] font-ui text-[10px] font-bold uppercase tracking-wider text-brand-600">
            {line.label}
          </span>
          <span className="flex-1 font-prose text-[13px] leading-relaxed text-ash-800">
            {line.text}
          </span>
        </li>
      ))}
    </ul>
  </div>
);

const JudgmentBlock = ({ cite, index, total, query }) => {
  const { status, answer, loading, notice, waiting, analyse } = useAnalysis(cite, query);
  const [showSummary, setShowSummary] = useState(false);
  const summaryLines = caseSummaryLines(cite.card);
  const ready = status === ANSWER_STATUS.READY && answer;
  const sections = ready ? meaningfulSections(answer) : [];
  const nothingToSay = ready && isEmptyAnswer(answer);
  const fit = ready && !nothingToSay ? fitSection(answer) : null;

  const renderAnalysis = () => {
    if (loading) {
      return (
        <p className="mt-4 flex items-center gap-2 font-prose text-[13px] italic text-ash-600">
          <span className="material-symbols-outlined animate-spin text-[18px] text-brand-500">
            progress_activity
          </span>
          Analysing this case against your description…
        </p>
      );
    }

    if (ready) {
      if (nothingToSay) {
        return (
          <p className="mt-4 rounded-xl border border-ash-200 bg-ash-50 px-4 py-3 font-prose text-[13px] text-ash-600">
            This judgment was retrieved as related, but it does not address the
            question directly. Read it in full before relying on it.
          </p>
        );
      }
      return (
        <>
          {sections.map((section, sIdx) => (
            <div key={sIdx} className="mt-4">
              {section.heading && (
                <h4 className="mb-1.5 font-display text-[11px] font-semibold uppercase tracking-wider text-brand-500">
                  {section.heading}
                </h4>
              )}
              <p className="whitespace-pre-line font-prose text-sm leading-relaxed text-ash-900">
                {section.body}
              </p>
            </div>
          ))}
          {fit && <FitCallout fit={fit} />}
        </>
      );
    }

    if (status === ANSWER_STATUS.RATE_LIMITED) {
      return (
        <>
          <CardSummary card={cite.card} />
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-amber-400/40 bg-amber-400/10 px-4 py-3">
            <span className="material-symbols-outlined text-[18px] text-ash-600">hourglass_top</span>
            <p className="flex-1 font-prose text-[13px] text-ash-700">
              {notice ||
                (waiting
                  ? 'The service is busy — retrying…'
                  : 'The service is busy. Please try again in a minute.')}
            </p>
            {query && (
              <button
                type="button"
                onClick={() => analyse()}
                className="inline-flex items-center gap-1 rounded-full border border-ash-300 bg-white px-3 py-1.5 font-ui text-[12px] font-semibold text-ash-700 transition-all hover:border-brand-300 hover:text-brand-700"
              >
                <span className="material-symbols-outlined text-[15px]">refresh</span>
                Retry now
              </button>
            )}
          </div>
        </>
      );
    }

    if (status === ANSWER_STATUS.ERROR) {
      return (
        <>
          <CardSummary card={cite.card} />
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-ash-200 bg-ash-50 px-4 py-3">
            <p className="flex-1 font-prose text-[13px] text-ash-600">
              The analysis could not be generated for this case. You can try again,
              or read the judgment in full.
            </p>
            {query && <AnalyseButton onClick={() => analyse()} label="Try again" icon="refresh" />}
          </div>
        </>
      );
    }

    // on_demand: what the case is now, its analysis when the reader asks.
    return (
      <>
        {cite.card ? (
          <CardSummary card={cite.card} />
        ) : (
          <p className="mt-4 font-prose text-[13px] text-ash-600">
            Not analysed yet. Analyse it to see what the Court held and how it
            compares with your situation.
          </p>
        )}
        {query && (
          <div className="mt-4">
            <AnalyseButton onClick={() => analyse()} label="Analyse this case" />
          </div>
        )}
      </>
    );
  };

  return (
    <div className={index > 0 ? 'mt-8 border-t border-ash-200 pt-7' : ''}>
      <div className="flex flex-wrap items-center gap-2.5">
        {total > 1 && (
          <span className="grad-brand flex h-6 w-6 items-center justify-center rounded-full font-display text-[11px] font-bold text-white">
            {index + 1}
          </span>
        )}
        <span className="font-display text-[15px] font-bold text-ash-900">
          {prettyCaseName(cite.filename, cite.judgment_id.slice(0, 8))}
        </span>
        <RelevanceBadge score={cite.similarity_score} confidence={cite.confidence} />
      </div>

      {cite.sections_retrieved?.length > 0 && (
        <p className="mt-1.5 text-xs text-ash-500">
          Matched in: {prettySections(cite.sections_retrieved)}
        </p>
      )}

      {/* The LLM judge's one-line reason, when the v2 judge ran. */}
      {cite.reason && (
        <p className="mt-1.5 font-prose text-xs italic text-ash-500">Why: {cite.reason}</p>
      )}

      {/* Works whether one case came back or many. */}
      {summaryLines && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowSummary((v) => !v)}
            aria-expanded={showSummary}
            className="inline-flex items-center gap-1.5 rounded-full border border-ash-300 bg-white px-3.5 py-1.5 font-ui text-[12px] font-semibold text-ash-700 transition-all hover:border-brand-300 hover:text-brand-700"
          >
            <span className="material-symbols-outlined text-[16px]">
              {showSummary ? 'expand_less' : 'summarize'}
            </span>
            {showSummary ? 'Hide summary' : 'Summary'}
          </button>
          {showSummary && <ThreeLineSummary lines={summaryLines} />}
        </div>
      )}

      {renderAnalysis()}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <DownloadButton cite={cite} />
        {/* Copies what is on screen: an on-demand analysis lives in this
            component's state, so the text is built here rather than from the
            stored message. */}
        <CopyButton
          text={() => judgmentShareText(cite, ready ? answer : cite.llm_answer, query)}
          label="Copy"
          copiedLabel="Copied"
          title="Copy this case and its analysis to share"
        />
      </div>
    </div>
  );
};

const ResultsPanel = ({ message }) => {
  const [showAll, setShowAll] = useState(false);
  const [compare, setCompare] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState('');

  const citations = message.citations || [];
  const many = citations.length > 1;

  // Filtering narrows what is DISPLAYED only. Compare deliberately still works
  // on the full result set, so narrowing the list cannot silently change what
  // a comparison covers.
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [showFilter, setShowFilter] = useState(false);
  const visible = many ? citations.filter((c) => matchesFilters(c, filters)) : citations;

  const runCompare = async () => {
    if (compare) {
      setCompare({ ...compare });
      return;
    }
    setComparing(true);
    setCompareError('');
    try {
      const res = await apiFetch('/query/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ judgment_ids: citations.map((c) => c.judgment_id) }),
      });
      if (res.status === 429) {
        setCompareError(
          (await errorDetail(res)) || 'The service is busy. Please try the comparison again in a minute.'
        );
        return;
      }
      if (!res.ok) throw new Error(`Comparison failed (${res.status})`);
      setCompare(await res.json());
    } catch (error) {
      console.error('Compare failed:', error);
      setCompareError('The comparison could not be built. Please try again.');
    } finally {
      setComparing(false);
    }
  };

  // ── Nothing was retrieved ────────────────────────────────────────────
  // The message and nothing else. No list, no downloads, no answer — the
  // whole point is that there is no authority to present.
  if (message.noResults || citations.length === 0) {
    return (
      <div className="rounded-2xl border border-ash-200 bg-ash-50 px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined mt-0.5 flex-shrink-0 text-[20px] text-ash-400">
            search_off
          </span>
          <p className="font-prose text-sm leading-relaxed text-ash-700">
            {message.text ||
              'No relevant case is available in our data centre for this query.'}
          </p>
        </div>
        <div className="mt-2 flex justify-end">
          <CopyButton
            text={
              message.text ||
              'No relevant case is available in our data centre for this query.'
            }
            title="Copy this reply"
          />
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* A broad query is answered with a list of judgments in that area, not
          an answer to one question; say so before the reader starts relying
          on any of them. */}
      {message.notice && (
        <div className="mb-5 flex items-start gap-2.5 rounded-2xl border border-brand-100 bg-brand-50 px-4 py-3">
          <span className="material-symbols-outlined mt-0.5 flex-shrink-0 text-[18px] text-brand-500">
            info
          </span>
          <p className="font-prose text-[13px] leading-relaxed text-ash-700">{message.notice}</p>
        </div>
      )}

      {message.text && (
        <p className="mb-5 whitespace-pre-line font-prose text-sm leading-relaxed text-ash-900">
          {message.text}
        </p>
      )}

      {/* A filter is in force: say so above the list, since the control that
          set it is at the bottom and may be scrolled out of view. */}
      {many && activeFilterCount(filters) > 0 && (
        <div className="mb-5 flex flex-wrap items-center gap-2.5 rounded-2xl border border-brand-100 bg-brand-50 px-4 py-2.5">
          <span className="material-symbols-outlined text-[17px] text-brand-500">filter_list</span>
          <span className="font-prose text-[13px] text-ash-700">
            Filtered: showing <strong>{visible.length}</strong> of {citations.length} judgments
          </span>
          <button
            type="button"
            onClick={() => setFilters(EMPTY_FILTERS)}
            className="ml-auto rounded-full border border-ash-300 bg-white px-3 py-1 font-ui text-[11px] font-bold text-ash-600 transition-colors hover:border-brand-300 hover:text-brand-700"
          >
            Clear
          </button>
        </div>
      )}

      {many && visible.length === 0 && (
        <div className="rounded-2xl border border-ash-200 bg-ash-50 px-5 py-4 font-prose text-sm text-ash-600">
          No retrieved judgment matches these filters.{' '}
          <button
            type="button"
            onClick={() => setFilters(EMPTY_FILTERS)}
            className="font-semibold text-brand-600 underline-offset-2 hover:underline"
          >
            Clear the filters
          </button>{' '}
          to see all {citations.length}.
        </div>
      )}

      {visible.map((cite, index) => (
        <JudgmentBlock
          key={cite.judgment_id}
          cite={cite}
          index={index}
          total={visible.length}
          query={message.query}
        />
      ))}

      {many && (
        <div className="mt-7 flex flex-wrap items-center gap-2.5 border-t border-ash-200 pt-5">
          <button
            type="button"
            onClick={() => setShowFilter(true)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 font-ui text-[13px] font-semibold transition-all ${
              activeFilterCount(filters)
                ? 'border-brand-300 bg-brand-50 text-brand-700'
                : 'border-ash-300 bg-white text-ash-700 hover:border-brand-300 hover:text-brand-700'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">filter_list</span>
            Filter
            {activeFilterCount(filters) > 0 && (
              <span className="ml-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand-600 px-1 font-ui text-[10px] font-bold text-white">
                {activeFilterCount(filters)}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="inline-flex items-center gap-1.5 rounded-full border border-ash-300 bg-white px-4 py-2 font-ui text-[13px] font-semibold text-ash-700 transition-all hover:border-brand-300 hover:text-brand-700"
          >
            <span className="material-symbols-outlined text-[16px]">library_books</span>
            See all {citations.length} judgments
          </button>

          <button
            type="button"
            onClick={runCompare}
            disabled={comparing}
            className="grad-btn inline-flex items-center gap-1.5 rounded-full px-4 py-2 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:-translate-y-0.5 hover:shadow-glow-lg disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span
              className={`material-symbols-outlined text-[16px] ${comparing ? 'animate-spin' : ''}`}
            >
              {comparing ? 'progress_activity' : 'compare_arrows'}
            </span>
            {comparing ? 'Comparing…' : 'Compare judgments'}
          </button>

          {/* Copies every judgment in this answer in one go. Only the analyses
              already drafted are included; one fetched on demand is copied
              from its own card. */}
          <CopyButton
            text={() => responseShareText(message)}
            label={`Copy all ${citations.length}`}
            copiedLabel="Copied"
            title="Copy every judgment in this answer"
          />

          {compareError && (
            <span className="font-prose text-xs text-error">{compareError}</span>
          )}
        </div>
      )}

      {message.latencyMs != null && (
        <p className="mt-3 text-xs text-ash-500">
          Retrieved in {(message.latencyMs / 1000).toFixed(1)}s
        </p>
      )}

      {showFilter && (
        <FilterDialog
          cases={citations}
          filters={filters}
          onApply={setFilters}
          onClose={() => setShowFilter(false)}
          Modal={Modal}
        />
      )}

      {showAll && (
        <Modal
          title="Authorities retrieved"
          subtitle={`${citations.length} judgments matched this query, ordered by relevance.`}
          onClose={() => setShowAll(false)}
        >
          <div className="flex flex-col gap-2.5">
            {citations.map((cite) => (
              <CiteRow key={cite.judgment_id} cite={cite} />
            ))}
          </div>
        </Modal>
      )}

      {compare && (
        <Modal
          wide
          title="Comparison"
          subtitle="Every field is taken from the judgment itself. An em dash means the judgment does not record it."
          onClose={() => setCompare(null)}
        >
          {compare.rate_limited && (
            <p className="mb-4 rounded-xl border border-amber-400/40 bg-amber-400/10 px-4 py-2.5 font-prose text-[13px] text-ash-700">
              The service is busy, so some columns could not be filled. Close this and
              compare again in a minute — completed columns are kept.
            </p>
          )}
          <CompareTable table={compare} />
        </Modal>
      )}
    </div>
  );
};

export default ResultsPanel;
