import { prettyOutcome } from './answerFormat';

const shortDate = (iso) => {
  const when = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(when.getTime())) return iso;
  return when.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

/**
 * The active filters as short labels ("Allowed", "1 Jan 2015 – 31 Dec 2020",
 * "Judge: Munib"), so the query box and the results banner can both say what
 * is being applied without opening the dialog.
 */
export const filterChips = (f) => {
  if (!f) return [];
  const chips = [];
  if (f.outcome) chips.push(prettyOutcome(f.outcome));
  if (f.from && f.to) chips.push(`${shortDate(f.from)} – ${shortDate(f.to)}`);
  else if (f.from) chips.push(`After ${shortDate(f.from)}`);
  else if (f.to) chips.push(`Before ${shortDate(f.to)}`);
  if (f.query?.trim()) chips.push(`Case or party: ${f.query.trim()}`);
  if (f.judge?.trim()) chips.push(`Judge: ${f.judge.trim()}`);
  return chips;
};

export default filterChips;
