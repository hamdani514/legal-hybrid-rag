import { caseJudges } from './answerFormat';

/*
 * Narrowing a multi-case result: by final decision, a date range, case number
 * and judge.
 *
 * Every field is optional and they combine with AND, so leaving one empty
 * simply does not constrain that dimension. Applied, they run on the server
 * over every case the search found (ResultsPanel's useFilteredPages, backed by
 * orchestrator.matches_filters, which mirrors matchesFilters below); only a
 * conversation saved without its query narrows the cases on screen instead.
 * No AI call either way.
 */

// Every final decision a case card can record (case_card.py).
export const OUTCOMES = ['allowed', 'partly_allowed', 'dismissed', 'disposed', 'remanded'];

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

// Titles that are not part of a judge's name (see orchestrator._JUDGE_TITLES).
const JUDGE_TITLES = new Set(['justice', 'mr', 'mrs', 'ms', 'miss', 'j', 'cj', 'hcj', 'acj', 'chief',
  'the', 'hon', 'honourable', 'honorable', 'sir', 'dr']);

/** Lower-case letters and digits only: "C_P_L_A_3031" -> "cpla3031". */
const compact = (text) => String(text || '').toLowerCase().replace(/[^a-z0-9]/g, '');

/** A field's words, dots removed first so "C.P.L.A." stays one word. */
const words = (text, drop) =>
  String(text || '').toLowerCase().replace(/\./g, '').split(/[^a-z0-9]+/)
    .filter((w) => w && !(drop && drop.has(w)));

/**
 * Does one result match the active filters? Empty fields never exclude.
 * Mirrors orchestrator.matches_filters, which applies the same rules on the
 * server: every word typed must appear, ignoring spaces, dots, underscores
 * and (for judges) titles such as "Justice" or "HCJ".
 */
export const matchesFilters = (cite, f) => {
  const card = cite.card || {};

  if (f.outcome && String(card.outcome || '') !== f.outcome) return false;

  const judgeWords = words(f.judge, JUDGE_TITLES);
  if (judgeWords.length) {
    const found = caseJudges(card).some((j) => judgeWords.every((w) => compact(j).includes(w)));
    if (!found) return false;
  }

  if (f.from || f.to) {
    const when = caseDate(card);
    // A judgment with no usable date cannot be shown to fall inside a range.
    if (!when) return false;
    if (f.from && when < new Date(`${f.from}T00:00:00`)) return false;
    if (f.to && when > new Date(`${f.to}T23:59:59`)) return false;
  }

  const queryWords = words(f.query);
  if (queryWords.length) {
    const hay = compact([card.case_display, cite.filename, cite.judgment_id, card.appellant,
                         card.respondent, card.subject].filter(Boolean).join(' '));
    if (!queryWords.every((w) => hay.includes(w))) return false;
  }
  return true;
};
