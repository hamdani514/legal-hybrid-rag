import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import apiFetch, { TOKEN_KEY } from '../../lib/api';
import CopyButton from './CopyButton';
import Modal from './Modal';
import FilterIcon from './FilterIcon';
import { toast } from '../../lib/toast';
import useToastOn from '../../lib/useToastOn';
import FilterDialog from './ResultsFilter';
import { EMPTY_FILTERS, activeFilterCount, matchesFilters } from '../lib/filters';
import { FreePlanNote, LockedButton, UpgradeDialog } from './LockedFeature';
import { refreshPlan, upgradeDetail, usePlan } from '../lib/plan';
import { filterChips } from '../lib/filterSummary';
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
 * A search shows at most ten judgments. When the backend found more relevant
 * ones (`message.hasMore`), "More relevant cases" fetches the next ten from
 * POST /query/more and appends them, up to 100 in all.
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
 *
 * The plan decides which tools work (lib/plan.js, enforced by the server).
 * On Free each result is its case-card summary; analyse, summarise, filter,
 * download, compare, see all, copy and "More relevant cases" are shown as
 * LockedButtons that open the upgrade dialog instead of being hidden.
 */

// How a rate-limited analysis retries by itself before leaving it to the user.
const AUTO_RETRY_DELAY_MS = 20000;
const MAX_AUTO_RETRIES = 3;

// POST /query/compare accepts at most this many judgments.
const MAX_COMPARE = 10;

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

const DownloadButton = ({ cite, block = false, can, onLocked }) =>
  can && !can('download') ? (
    <LockedButton feature="download" icon="download" label="Download PDF" size="sm" onLocked={onLocked} />
  ) : (
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

const CiteRow = ({ cite, can, onLocked }) => (
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
      <DownloadButton cite={cite} can={can} onLocked={onLocked} />
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
const useAnalysis = (cite, query, onLocked) => {
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
        if (await upgradeDetail(res)) {
          // The plan does not include analysis (it changed since the page
          // loaded): back to the unanalysed state, and say why.
          setState((s) => ({ ...s, status: ANSWER_STATUS.ON_DEMAND, loading: false, notice: '' }));
          refreshPlan();
          onLocked?.('analyse');
          return;
        }
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
        toast.error('The analysis could not be generated. Please try again.');
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
        toast.error('The analysis could not be generated. Please try again.');
      }
    },
    [query, cite.judgment_id, onLocked]
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

const JudgmentBlock = ({ cite, index, total, query, can, onLocked }) => {
  const { status, answer, loading, notice, waiting, analyse } = useAnalysis(cite, query, onLocked);
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
            {can('analyse')
              ? 'Not analysed yet. Analyse it to see what the Court held and how it compares with your situation.'
              : 'A short summary of this case is not available yet.'}
          </p>
        )}
        {query && (
          <div className="mt-4">
            {can('analyse') ? (
              <AnalyseButton onClick={() => analyse()} label="Analyse this case" />
            ) : (
              <LockedButton feature="analyse" icon="auto_awesome" label="Analyse this case" onLocked={onLocked} />
            )}
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
      {summaryLines && !can('summarize') && (
        <div className="mt-3">
          <LockedButton feature="summarize" icon="summarize" label="Summary" size="sm" onLocked={onLocked} />
        </div>
      )}
      {summaryLines && can('summarize') && (
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
        <DownloadButton cite={cite} can={can} onLocked={onLocked} />
        {/* Copies what is on screen: an on-demand analysis lives in this
            component's state, so the text is built here rather than from the
            stored message. */}
        {can('copy') ? (
          <CopyButton
            text={() => judgmentShareText(cite, ready ? answer : cite.llm_answer, query)}
            label="Copy"
            copiedLabel="Copied"
            title="Copy this case and its analysis to share"
          />
        ) : (
          <LockedButton feature="copy" icon="content_copy" label="Copy" size="sm" onLocked={onLocked} />
        )}
      </div>
    </div>
  );
};

/**
 * "More relevant cases": the next page of this search, from POST /query/more.
 * Pages live in this component; a reopened conversation starts again from the
 * first page, and the button fetches the rest the same way.
 */
const useMorePages = (message, onLocked) => {
  const [extra, setExtra] = useState([]);
  const [hasMore, setHasMore] = useState(Boolean(message.hasMore && message.query));
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');

  const citations = [...(message.citations || []), ...extra];

  const loadMore = async () => {
    setLoading(true);
    setNotice('');
    try {
      const res = await apiFetch('/query/more', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: message.query,
          shown: citations.map((c) => c.judgment_id),
          top_k_sections: 3,
        }),
      });
      if (await upgradeDetail(res)) {
        refreshPlan();
        onLocked?.('see_all');
        return;
      }
      if (res.status === 429) {
        const busy = (await errorDetail(res)) || 'The service is busy. Please try again in a minute.';
        setNotice(busy);
        toast.error(busy);
        return;
      }
      if (!res.ok) throw new Error(`More results failed (${res.status})`);
      const data = await res.json();
      const seen = new Set(citations.map((c) => c.judgment_id));
      const fresh = (data.judgments || []).filter((j) => !seen.has(j.judgment_id));
      setExtra((prev) => [...prev, ...fresh]);
      if (fresh.length) toast.success(`${fresh.length} more relevant ${fresh.length === 1 ? 'case' : 'cases'} loaded.`);
      setHasMore(Boolean(data.has_more) && fresh.length > 0);
      if (fresh.length === 0) setNotice('No further relevant cases were found.');
    } catch (error) {
      console.error('More results failed:', error);
      setNotice('More cases could not be loaded. Please try again.');
      toast.error('More cases could not be loaded. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return { citations, hasMore, loading, notice, loadMore };
};

/**
 * Filtered results, from the server.
 *
 * Filters apply to EVERY case the search found, not only the ten on screen:
 * POST /query/more with `filters` returns the top ten matching cases, in
 * relevance order, and "More relevant cases" asks for the next ten that match
 * (`shown` = what the filtered list already holds). `view` is null while no
 * filter is applied, and the unfiltered list is kept untouched underneath, so
 * clearing the filters returns to it at once.
 *
 * `initialFilters` are those chosen with the query in the query box. The search
 * itself ran without them; the panel opens already filtering, showing the
 * "applying" state rather than a flash of the unfiltered list.
 */
// Restoring the filters a search was sent with is one request, however often
// the panel mounts: StrictMode mounts it twice in development, and a remount
// (a reopened conversation, a re-render of the list) must not re-run a search
// that is already on its way or just answered. Keyed by query and filters;
// kept while in flight and briefly after, then a reopen fetches fresh results.
const RESTORE_REUSE_MS = 10_000;
const restoreRequests = new Map();
const restoreOnce = (query, filters, run) => {
  const key = JSON.stringify([query, filters]);
  const hit = restoreRequests.get(key);
  if (hit && (hit.pending || Date.now() - hit.at < RESTORE_REUSE_MS)) return hit.promise;
  const entry = { pending: true, at: 0 };
  entry.promise = run().then(
    (out) => {
      Object.assign(entry, { pending: false, at: Date.now() });
      return out;
    },
    (error) => {
      restoreRequests.delete(key); // a failure is not reused: the next mount tries again
      throw error;
    }
  );
  restoreRequests.set(key, entry);
  return entry.promise;
};

const useFilteredPages = (message, onLocked, initialFilters) => {
  const [view, setView] = useState(() =>
    initialFilters
      ? { filters: initialFilters, citations: [], hasMore: false, loading: true, notice: '' }
      : null
  );

  const request = async (filters, shown, silent = false) => {
    const res = await apiFetch('/query/more', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: message.query, shown, top_k_sections: 3, filters }),
    });
    if (await upgradeDetail(res)) {
      refreshPlan();
      if (!silent) onLocked?.('filter');
      return { locked: true };
    }
    if (res.status === 429) {
      return { notice: (await errorDetail(res)) || 'The service is busy. Please try again in a minute.' };
    }
    if (!res.ok) throw new Error(`Filtering failed (${res.status})`);
    return { data: await res.json() };
  };

  // The first filtered page. `silent`: filters that came with the conversation,
  // not a click, so no toast and no upgrade prompt. Resolves to true when the
  // plan does not include filtering.
  const firstPage = async (filters, silent = false) => {
    // Ignore the answer if the filters changed while it was on its way.
    const settle = (patch) =>
      setView((v) => (v && v.filters === filters ? { ...v, loading: false, ...patch } : v));
    try {
      const out = silent
        ? await restoreOnce(message.query, filters, () => request(filters, [], true))
        : await request(filters, [], false);
      if (out.locked) {
        setView(null);
        return true;
      }
      if (out.notice) {
        toast.error(out.notice);
        settle({ notice: out.notice });
        return false;
      }
      const found = out.data.judgments || [];
      settle({ citations: found, hasMore: Boolean(out.data.has_more) });
      if (!silent) {
        toast.success(
          found.length
            ? `Filters applied: ${found.length}${out.data.has_more ? '+' : ''} matching ${found.length === 1 ? 'case' : 'cases'}.`
            : 'No case found for this search matches these filters.'
        );
      }
    } catch (error) {
      console.error('Filtering failed:', error);
      toast.error('The filters could not be applied. Please try again.');
      settle({ notice: 'The filters could not be applied. Please try again.' });
    }
    return false;
  };

  const start = (filters) => {
    setView({ filters, citations: [], hasMore: false, loading: true, notice: '' });
    return firstPage(filters);
  };

  const loadMore = async () => {
    if (!view || view.loading) return;
    const { filters } = view;
    const shownIds = view.citations.map((c) => c.judgment_id);
    setView((v) => ({ ...v, loading: true, notice: '' }));
    const settle = (patch) =>
      setView((v) => (v && v.filters === filters ? { ...v, loading: false, ...patch } : v));
    try {
      const out = await request(filters, shownIds);
      if (out.locked) return settle({});
      if (out.notice) {
        toast.error(out.notice);
        return settle({ notice: out.notice });
      }
      const seen = new Set(shownIds);
      const fresh = (out.data.judgments || []).filter((j) => !seen.has(j.judgment_id));
      setView((v) =>
        v && v.filters === filters
          ? {
              ...v,
              loading: false,
              citations: [...v.citations, ...fresh],
              hasMore: Boolean(out.data.has_more) && fresh.length > 0,
              notice: fresh.length ? '' : 'No further matching cases were found.',
            }
          : v
      );
      if (fresh.length) toast.success(`${fresh.length} more matching ${fresh.length === 1 ? 'case' : 'cases'} loaded.`);
    } catch (error) {
      console.error('More filtered results failed:', error);
      toast.error('More cases could not be loaded. Please try again.');
      settle({ notice: 'More cases could not be loaded. Please try again.' });
    }
    return undefined;
  };

  return { view, start, firstPage, loadMore, clear: () => setView(null) };
};

/** The bar under the list: how many cases are shown, and the button for more. */
const MoreBar = ({ count, hasMore, loading, notice, onMore, locked, onLocked }) => (
  <div className="mt-7 flex flex-wrap items-center gap-3 rounded-2xl border border-ash-200 bg-ash-50/70 px-4 py-3">
    <span className="font-prose text-[13px] text-ash-600">
      Showing <strong className="text-ash-900">{count}</strong> {count === 1 ? 'case' : 'cases'}
      {locked && hasMore && <span className="ml-2 text-ash-500">· more relevant cases were found</span>}
      {notice && <span className="ml-2 text-ash-500">· {notice}</span>}
    </span>
    {hasMore && locked && (
      <span className="ml-auto">
        <LockedButton feature="see_all" icon="expand_more" label="More relevant cases" onLocked={onLocked} />
      </span>
    )}
    {hasMore && !locked && (
      <button
        type="button"
        onClick={onMore}
        disabled={loading}
        className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-brand-300 bg-white px-4 py-2 font-ui text-[13px] font-semibold text-brand-700 transition-all hover:-translate-y-0.5 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span className={`material-symbols-outlined text-[16px] ${loading ? 'animate-spin' : ''}`}>
          {loading ? 'progress_activity' : 'expand_more'}
        </span>
        {loading ? 'Finding more cases…' : 'More relevant cases'}
      </button>
    )}
  </div>
);

const ResultsPanel = ({ message }) => {
  const [showAll, setShowAll] = useState(false);
  const [compare, setCompare] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState('');
  useToastOn(compareError, 'error');

  // What the plan unlocks, and the dialog a locked tool opens.
  const plan = usePlan();
  const can = useCallback((feature) => Boolean(plan.features[feature]), [plan]);
  const [lockedFeature, setLockedFeature] = useState(null);
  const onLocked = useCallback((feature) => setLockedFeature(feature), []);
  const more = useMorePages(message, onLocked);

  const citations = more.citations;
  const many = citations.length > 1;
  // Compare reads the leading judgments only: the endpoint takes at most ten.
  const compared = citations.slice(0, MAX_COMPARE);

  // Filters apply to every case the search found (useFilteredPages, on the
  // server). A conversation saved without its query cannot ask the server, so
  // it narrows the cases on screen instead. Compare, "See all" and "Copy all"
  // keep working on the unfiltered results, so a filter cannot silently
  // change what they cover.
  const initialFilters =
    message.query && message.citations?.length && activeFilterCount(message.filters) > 0
      ? message.filters
      : null;
  const [filters, setFilters] = useState(initialFilters || EMPTY_FILTERS);
  const [showFilter, setShowFilter] = useState(false);
  const filtering = useFilteredPages(message, onLocked, initialFilters);
  const restored = useRef(false);
  useEffect(() => {
    // Once per message (StrictMode runs effects twice). A plan that no longer
    // includes filtering simply shows the plain results.
    if (!initialFilters || restored.current) return;
    restored.current = true;
    filtering.firstPage(initialFilters, true).then((locked) => {
      if (locked) setFilters(EMPTY_FILTERS);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const serverFiltered = Boolean(filtering.view);
  const filterOn = activeFilterCount(filters) > 0;
  // A case also on the first page keeps what it has there: its analysis and
  // its match label.
  const firstById = new Map(citations.map((c) => [c.judgment_id, c]));
  const visible = serverFiltered
    ? filtering.view.citations.map((c) => firstById.get(c.judgment_id) || c)
    : many
      ? citations.filter((c) => matchesFilters(c, filters))
      : citations;

  const applyFilters = (next) => {
    setFilters(next);
    if (activeFilterCount(next) > 0 && message.query) filtering.start(next);
    else filtering.clear();
  };
  const clearFilters = () => applyFilters(EMPTY_FILTERS);

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
        body: JSON.stringify({ judgment_ids: compared.map((c) => c.judgment_id) }),
      });
      if (await upgradeDetail(res)) {
        refreshPlan();
        onLocked('compare');
        return;
      }
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
            {message.limitReached ? 'hourglass_disabled' : 'search_off'}
          </span>
          <p className="font-prose text-sm leading-relaxed text-ash-700">
            {message.text ||
              'No relevant case is available in our data centre for this query.'}
          </p>
        </div>
        {/* Nothing was retrieved, so there is nothing worth copying. */}
        {message.limitReached && (
          <div className="mt-3">
            <Link
              to="/pricing"
              className="inline-flex items-center gap-1 rounded-full bg-brand-600 px-3.5 py-1.5 font-ui text-[12px] font-bold text-white shadow-xs transition-all hover:-translate-y-0.5 hover:bg-brand-700"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">workspace_premium</span>
              See plans
            </Link>
          </div>
        )}
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
      {(many || serverFiltered) && filterOn && (
        <div className="mb-5 flex flex-wrap items-center gap-2.5 rounded-2xl border border-brand-100 bg-brand-50 px-4 py-2.5">
          <FilterIcon size={15} className="text-brand-500" />
          <span className="font-prose text-[13px] text-ash-700">
            {serverFiltered ? (
              filtering.view.loading && visible.length === 0 ? (
                'Filtering every case found for this search…'
              ) : (
                <>
                  Filtered: <strong>{visible.length}</strong> matching{' '}
                  {visible.length === 1 ? 'case' : 'cases'} from all results for this search
                </>
              )
            ) : (
              <>
                Filtered: showing <strong>{visible.length}</strong> of {citations.length} judgments
              </>
            )}
          </span>
          <button
            type="button"
            onClick={clearFilters}
            className="ml-auto rounded-full border border-ash-300 bg-white px-3 py-1 font-ui text-[11px] font-bold text-ash-600 transition-colors hover:border-brand-300 hover:text-brand-700"
          >
            Reset filters
          </button>
          <div className="flex w-full flex-wrap gap-1.5">
            {filterChips(filters).map((chip) => (
              <span
                key={chip}
                className="rounded-full bg-white px-2.5 py-0.5 font-ui text-[11px] font-semibold text-brand-700 ring-1 ring-brand-100"
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
      )}

      {serverFiltered && filtering.view.loading && visible.length === 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-ash-200 bg-ash-50 px-5 py-4">
          <span aria-hidden="true" className="material-symbols-outlined animate-spin text-[20px] text-brand-500">
            progress_activity
          </span>
          <p className="font-prose text-sm text-ash-600" role="status">
            Applying your filters to every case found for this search…
          </p>
        </div>
      )}

      {(many || serverFiltered) && visible.length === 0 && !(serverFiltered && filtering.view.loading) && (
        <div className="rounded-2xl border border-ash-200 bg-ash-50 px-5 py-4 font-prose text-sm text-ash-600">
          {serverFiltered
            ? filtering.view.notice || 'No case found for this search matches these filters.'
            : 'No retrieved judgment matches these filters.'}{' '}
          <button
            type="button"
            onClick={clearFilters}
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
          can={can}
          onLocked={onLocked}
        />
      ))}

      {serverFiltered
        ? visible.length > 0 && (
            <MoreBar
              count={visible.length}
              hasMore={filtering.view.hasMore}
              loading={filtering.view.loading}
              notice={filtering.view.notice}
              onMore={filtering.loadMore}
              locked={false}
              onLocked={onLocked}
            />
          )
        : (many || more.hasMore) && (
            <MoreBar
              count={citations.length}
              hasMore={more.hasMore}
              loading={more.loading}
              notice={more.notice}
              onMore={more.loadMore}
              locked={!can('see_all')}
              onLocked={onLocked}
            />
          )}

      {(many || filterOn) && (
        <div className="mt-7 flex flex-wrap items-center gap-2.5 border-t border-ash-200 pt-5">
          {!can('filter') ? (
            <LockedButton feature="filter" icon={<FilterIcon size={15} />} label="Filter" onLocked={onLocked} />
          ) : (
          <button
            type="button"
            onClick={() => setShowFilter(true)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 font-ui text-[13px] font-semibold transition-all ${
              activeFilterCount(filters)
                ? 'border-brand-300 bg-brand-50 text-brand-700'
                : 'border-ash-300 bg-white text-ash-700 hover:border-brand-300 hover:text-brand-700'
            }`}
          >
            <FilterIcon size={15} />
            Filter
            {activeFilterCount(filters) > 0 && (
              <span className="ml-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand-600 px-1 font-ui text-[10px] font-bold text-white">
                {activeFilterCount(filters)}
              </span>
            )}
          </button>
          )}

          {!can('see_all') ? (
            <LockedButton
              feature="see_all"
              icon="library_books"
              label={`See all ${citations.length} judgments`}
              onLocked={onLocked}
            />
          ) : (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="inline-flex items-center gap-1.5 rounded-full border border-ash-300 bg-white px-4 py-2 font-ui text-[13px] font-semibold text-ash-700 transition-all hover:border-brand-300 hover:text-brand-700"
          >
            <span className="material-symbols-outlined text-[16px]">library_books</span>
            See all {citations.length} judgments
          </button>
          )}

          {!can('compare') ? (
            <LockedButton feature="compare" icon="compare_arrows" label="Compare judgments" onLocked={onLocked} />
          ) : (
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
            {comparing
              ? 'Comparing…'
              : citations.length > MAX_COMPARE
                ? `Compare top ${MAX_COMPARE}`
                : 'Compare judgments'}
          </button>
          )}

          {/* Copies every judgment in this answer in one go. Only the analyses
              already drafted are included; one fetched on demand is copied
              from its own card. */}
          {can('copy') ? (
            <CopyButton
              text={() => responseShareText({ ...message, citations })}
              label={`Copy all ${citations.length}`}
              copiedLabel="Copied"
              title="Copy every judgment in this answer"
            />
          ) : (
            <LockedButton
              feature="copy"
              icon="content_copy"
              label={`Copy all ${citations.length}`}
              onLocked={onLocked}
            />
          )}

          {compareError && (
            <span className="font-prose text-xs text-error">{compareError}</span>
          )}
        </div>
      )}

      {plan.key === 'free' && <FreePlanNote />}

      {message.latencyMs != null && (
        <p className="mt-3 text-xs text-ash-500">
          Retrieved in {(message.latencyMs / 1000).toFixed(1)}s
        </p>
      )}

      {showFilter && (
        <FilterDialog
          cases={citations}
          filters={filters}
          onApply={applyFilters}
          searchesAll={Boolean(message.query)}
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
              <CiteRow key={cite.judgment_id} cite={cite} can={can} onLocked={onLocked} />
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

      {lockedFeature && (
        <UpgradeDialog feature={lockedFeature} onClose={() => setLockedFeature(null)} />
      )}
    </div>
  );
};

export default ResultsPanel;
