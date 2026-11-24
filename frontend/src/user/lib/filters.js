import { caseJudges } from './answerFormat';

/*
 * Narrowing a multi-case result: by final decision, a date range, case number,
 * judge and legal section.
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

export const EMPTY_FILTERS = { outcome: '', judge: '', from: '', to: '', query: '', section: '' };

/** How many fields are actually constraining the list (for the button badge). */
export const activeFilterCount = (f) =>
  ['outcome', 'judge', 'from', 'to', 'query', 'section'].filter((k) => (f?.[k] || '').trim()).length;

/*
 * The Section filter. Mirrors app/retrieval/case_sections.py (parse_terms,
 * _provision_matches): keep the two in step. A case matches when, for every
 * term typed ("302, 34" = both), one of its provisions (card.provisions, sent
 * by the server) matches it:
 *   302          any section 302: 302 PPC, 302(b) PPC ...
 *   302(b)       302(b) only, not 302(c)        302 b   302(b), or a section 302-B
 *   489-F, 489F  the lettered section           302 PPC only the PPC's section 302
 *   Article 199  articles by name ("Art. 199" too)
 * Words that are not a provision ("murder") do not narrow anything.
 */
// The letter may lack its hyphen ("377B" from older lists): one form, "377-B".
const PROVISION_RE = /^(Section|Article|Order)\s+(\d{1,4}(?:-?[A-Z](?![A-Z]))?)((?:\([0-9a-z]{1,4}\))*)\s*(.*)$/i;
const sectionNumber = (value) => {
  const v = value.toUpperCase();
  return /[A-Z]$/.test(v) ? `${v.slice(0, -1).replace(/-$/, '')}-${v.slice(-1)}` : v;
};
const TERM_RE =
  /^\s*(?:(sections?|secs?\.?|ss?\.|s\.?|u\/s\.?|articles?|arts?\.?|art|orders?)\s*)?(\d{1,4})\s*(?:-?\s*([a-z])(?![a-z]))?\s*((?:\(\s*[0-9a-z]{1,4}\s*\))*)\s*(.*?)\s*$/i;
const CODE_WORDS = {
  pakistanpenalcode: 'ppc', penalcode: 'ppc',
  codeofcriminalprocedure: 'crpc', criminalprocedurecode: 'crpc',
  codeofcivilprocedure: 'cpc', civilprocedurecode: 'cpc',
  qanuneshahadat: 'qso', qanuneshahadatorder: 'qso',
  controlofnarcoticsubstancesact: 'cnsa', antiterrorismact: 'ata',
};
const codeKey = (text) => {
  const key = String(text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return CODE_WORDS[key] || key;
};

/** The Section filter's terms: "302, 34 PPC" -> two terms. */
export const parseSectionTerms = (typed) =>
  String(typed || '')
    .split(/[,;&]|\band\b/i)
    .map((raw) => {
      const m = TERM_RE.exec(raw.replace(/–/g, '-'));
      if (!m) return null;
      const kindWord = (m[1] || '').toLowerCase();
      const kind = kindWord.startsWith('art') ? 'article' : kindWord.startsWith('order') ? 'order' : 'section';
      return {
        kind,
        number: m[2] + (m[3] ? `-${m[3].toUpperCase()}` : ''),
        subs: (m[4] || '').replace(/\s+/g, '').toLowerCase(),
        code: codeKey((m[5] || '').trim().replace(/^of\s+(?:the\s+)?/i, '')),
      };
    })
    .filter(Boolean);

const provisionMatches = (provision, term) => {
  const p = PROVISION_RE.exec(provision);
  if (!p || p[1].toLowerCase() !== term.kind) return false;
  const number = sectionNumber(p[2]);
  const subs = p[3].toLowerCase();
  if (number !== term.number) {
    // A letter is written both ways: "302 b" for 302(b), "9-C" for 9(c).
    const [base, letter] = term.number.split('-');
    const [pBase, pLetter] = number.split('-');
    const typedLetter = letter && !term.subs && number === base && subs.startsWith(`(${letter.toLowerCase()})`);
    const judgmentLetter = pLetter && !subs && pBase === term.number && term.subs.startsWith(`(${pLetter.toLowerCase()})`);
    if (!(typedLetter || judgmentLetter)) return false;
  } else if (term.subs && !subs.startsWith(term.subs)) {
    return false;
  }
  if (term.code) {
    const code = codeKey(p[4]);
    if (!code.includes(term.code) && !term.code.includes(code)) return false;
  }
  return true;
};

/** Does a case involve every section typed? Empty or unreadable input never excludes. */
export const matchesSections = (card, typed) => {
  const terms = parseSectionTerms(typed);
  if (!terms.length) return true;
  const have = Array.isArray(card?.provisions) ? card.provisions : [];
  return terms.every((t) => have.some((p) => provisionMatches(p, t)));
};

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

  if (!matchesSections(card, f.section)) return false;
  return true;
};
