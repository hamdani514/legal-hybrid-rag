/**
 * Parsing for the structured answers the retrieval pipeline generates.
 *
 * The responder is asked for five headings. Models wrap them inconsistently
 * ("[LEGAL ISSUE]", "**[LEGAL ISSUE]**", "**LEGAL ISSUE**"), so the label is
 * matched and the decoration around it ignored.
 */

const HEADING_RE =
  /^\s*\**\s*\[?\s*(RELEVANT FACTS|LEGAL ISSUE|COURT REASONING|FINAL DECISION|KEY PRINCIPLE|FIT WITH YOUR SITUATION)\s*\]?\s*\**\s*:?\s*$/i;

/** The marker the responder emits when the judgments do not address the query. */
export const NO_AUTHORITY_MARKER = '[NO RELEVANT AUTHORITY]';

/** What the responder writes into a heading it cannot fill from the text. */
const NOT_FOUND = 'not found in retrieved judgments';

const stripEmphasis = (line) => line.replace(/\*\*/g, '').trimEnd();

/**
 * Split a generated answer into `{ heading, body }` blocks. An answer with no
 * recognisable headings comes back as a single unlabelled block.
 */
export const parseAnswer = (answer) => {
  const sections = [];
  let current = null;

  for (const rawLine of (answer || '').split('\n')) {
    const match = rawLine.match(HEADING_RE);
    if (match) {
      current = { heading: match[1].toUpperCase(), lines: [] };
      sections.push(current);
    } else if (current) {
      current.lines.push(stripEmphasis(rawLine));
    } else if (rawLine.trim()) {
      current = { heading: null, lines: [stripEmphasis(rawLine)] };
      sections.push(current);
    }
  }

  return sections
    .map((s) => ({ heading: s.heading, body: s.lines.join('\n').trim() }))
    .filter((s) => s.heading || s.body);
};

/**
 * True when an answer says, in substance, that it found nothing.
 *
 * Two shapes count. The responder may emit the explicit marker, or it may fill
 * every heading with "Not found in retrieved judgments." Both mean the same
 * thing to a reader, and neither should be rendered as though it were an
 * answer with one stray field populated.
 */
export const isEmptyAnswer = (answer) => {
  if (!answer) return true;
  if (answer.includes(NO_AUTHORITY_MARKER)) return true;

  // The fit check is about the user's case, not the judgment; it cannot make
  // an otherwise empty analysis non-empty.
  const sections = parseAnswer(answer).filter(
    (s) => s.heading && s.heading !== 'FIT WITH YOUR SITUATION'
  );
  if (!sections.length) return false;

  return sections.every((s) => s.body.toLowerCase().includes(NOT_FOUND));
};

/**
 * The heading where the model checks the judgment against the user's own
 * description. Rendered apart from the analysis (it is about the user's case,
 * not the judgment), and dropped when the query was a plain question.
 */
export const FIT_HEADING = 'FIT WITH YOUR SITUATION';

const isNotApplicable = (body) => /^not applicable\b/i.test(body.trim());

/** Drop the headings a judgment did not support, so gaps are not rendered. */
export const meaningfulSections = (answer) =>
  parseAnswer(answer).filter(
    (s) =>
      s.body &&
      s.heading !== FIT_HEADING &&
      !s.body.toLowerCase().includes(NOT_FOUND)
  );

/**
 * The fit check as `{ verdict, body }`, or null when there is none to show.
 * verdict: 'distinguishable' | 'matches' | 'partial'.
 */
export const fitSection = (answer) => {
  const fit = parseAnswer(answer).find((s) => s.heading === FIT_HEADING);
  if (!fit || !fit.body || isNotApplicable(fit.body)) return null;
  if (fit.body.toLowerCase().includes(NOT_FOUND)) return null;
  const lead = fit.body.trim().toLowerCase();
  const verdict = lead.startsWith('distinguishable')
    ? 'distinguishable'
    : lead.startsWith('closely matches')
      ? 'matches'
      : 'partial';
  return { verdict, body: fit.body };
};

/**
 * Answer states, mirroring contracts.ANSWER_STATUSES on the backend. The UI
 * renders by these, never by looking for error text inside an answer.
 */
export const ANSWER_STATUS = {
  READY: 'ready',
  ON_DEMAND: 'on_demand',
  RATE_LIMITED: 'rate_limited',
  ERROR: 'error',
};

/** The status of a result, inferring one for responses from an older backend. */
export const answerStatusOf = (cite) => {
  if (cite?.answer_status) return cite.answer_status;
  return cite?.llm_answer ? ANSWER_STATUS.READY : ANSWER_STATUS.ON_DEMAND;
};

/** Outcome labels from case cards ("dismissed") shown as "Dismissed". */
export const prettyOutcome = (outcome) => {
  if (!outcome || typeof outcome !== 'string' || outcome === 'unknown') return '';
  return outcome.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
};

/** "judgement_C_A_42-K_2016.pdf" -> "C.A. 42-K 2016" */
export const prettyCaseName = (filename, fallback = '') => {
  if (!filename) return fallback;
  const base = filename.replace(/\.pdf$/i, '').replace(/^judge?ment[_-]?/i, '');
  return base.replace(/_/g, ' ').replace(/\bC A\b/, 'C.A.').replace(/\bC P L A\b/, 'C.P.L.A.').trim();
};

/** Section labels come back as HEADER_CORAM; show them as "header coram". */
export const prettySections = (sections = []) =>
  sections.map((s) => s.replace(/_/g, ' ').toLowerCase()).join(', ');

/** Confidence labels, shared by the badge and the copied text. */
export const CONFIDENCE_LABEL = {
  high: 'Strong match',
  medium: 'Possible match — verify',
  related: 'Related case',
};

/**
 * One judgment as plain text, for sharing outside the app.
 *
 * Mirrors what the result card shows on screen - the case, how confident the
 * system is, the analysis under its headings, and the fit with the user's own
 * situation - so what is pasted into an email matches what was read here. The
 * verification line is deliberate: a pasted extract loses the badge, and a
 * "possible match" must not travel as though it were settled law.
 */
export const judgmentShareText = (cite, answer, query) => {
  if (!cite) return '';
  const name = prettyCaseName(cite.filename, (cite.judgment_id || '').slice(0, 8));
  const label = CONFIDENCE_LABEL[cite.confidence] || '';
  const out = [label ? `${name} — ${label}` : name];

  if (query) out.push('', `Question asked: ${query.trim()}`);

  for (const section of answer ? meaningfulSections(answer) : []) {
    out.push('', section.heading || '', section.body);
  }
  const fit = answer ? fitSection(answer) : null;
  if (fit) out.push('', FIT_HEADING, fit.body);

  if (cite.filename) out.push('', `Source judgment: ${cite.filename}`);
  out.push(
    'Retrieved with Verdict AI from reported judgments of the Supreme Court of Pakistan.',
    'Verify against the original judgment before relying on it.',
  );
  return out.filter((line, i) => line !== '' || out[i - 1] !== '').join('\n').trim();
};

/** Every judgment in one response as plain text, for sharing the whole answer. */
export const responseShareText = (message, answers = {}) => {
  const cites = message?.citations || [];
  if (!cites.length) return (message?.text || '').trim();
  const query = message.query || '';
  const header = query ? [`Question asked: ${query.trim()}`, ''] : [];
  const blocks = cites.map((c) =>
    judgmentShareText({ ...c }, answers[c.judgment_id] ?? c.llm_answer, '')
  );
  return [...header, blocks.join('\n\n----------------------------------------\n\n')].join('\n').trim();
};
