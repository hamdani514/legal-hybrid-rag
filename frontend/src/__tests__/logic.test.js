// The rules that decide what a user sees: which cases a filter keeps, what a
// plan unlocks, how a case is named and how chat addresses are built.
// Run with `npm test`; the Docker build runs them too, so a failure stops it.
import { describe, expect, it } from 'vitest';
import { EMPTY_FILTERS, activeFilterCount, caseDate, matchesFilters } from '../user/lib/filters';
import { filterChips } from '../user/lib/filterSummary';
import { FEATURES, PLANS, planKey } from '../user/lib/plan';
import { slugify, slugifyTyping } from '../lib/slug';
import { chatPath, chatSlug, slugMatches } from '../user/lib/chatSlug';
import { caseJudges, isEmptyAnswer, prettyCaseName, prettyOutcome, NO_AUTHORITY_MARKER } from '../user/lib/answerFormat';

const cite = {
  judgment_id: 'abc',
  filename: 'judgement_C_P_L_A_3031_2021.pdf',
  card: {
    case_display: 'Civil Petition No. 3031 of 2021',
    outcome: 'allowed',
    decision_date: '04.05.2021',
    bench: ['Justice Mian Saqib Nisar, HCJ', 'Justice Yahya Afridi'],
    appellant: 'Maqbool Ahmed Mahessar & 2 others',
    respondent: 'NAB through its Chairman',
  },
};
const f = (over) => ({ ...EMPTY_FILTERS, ...over });

describe('filters', () => {
  it('an empty filter keeps everything', () => {
    expect(matchesFilters(cite, EMPTY_FILTERS)).toBe(true);
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
  });

  it('case number: spacing, dots and slashes do not matter', () => {
    for (const q of ['C.P.L.A. 3031 2021', 'CPLA 3031/2021', '3031 of 2021', 'cpla3031']) {
      expect(matchesFilters(cite, f({ query: q }))).toBe(true);
    }
    expect(matchesFilters(cite, f({ query: 'C.P.L.A. 3032 2021' }))).toBe(false);
  });

  it('party names match on every word typed', () => {
    expect(matchesFilters(cite, f({ query: 'Maqbool Ahmed' }))).toBe(true);
    expect(matchesFilters(cite, f({ query: 'Maqbool Khan' }))).toBe(false);
  });

  it('judge: titles are optional, one judge must carry every word', () => {
    for (const j of ['afridi', 'Yahya Afridi', 'Justice Yahya Afridi', 'Saqib Nisar CJ']) {
      expect(matchesFilters(cite, f({ judge: j }))).toBe(true);
    }
    expect(matchesFilters(cite, f({ judge: 'Yahya Nisar' }))).toBe(false);
  });

  it('date range: DD.MM.YYYY dates are read correctly', () => {
    expect(caseDate(cite.card).getMonth()).toBe(4); // May, not April
    expect(matchesFilters(cite, f({ from: '2021-05-01', to: '2021-05-31' }))).toBe(true);
    expect(matchesFilters(cite, f({ from: '2021-05-05' }))).toBe(false);
    expect(matchesFilters({ ...cite, card: { ...cite.card, decision_date: '' } }, f({ from: '2020-01-01' }))).toBe(false);
  });

  it('decision must match exactly', () => {
    expect(matchesFilters(cite, f({ outcome: 'allowed' }))).toBe(true);
    expect(matchesFilters(cite, f({ outcome: 'dismissed' }))).toBe(false);
  });

  it('active filters read as short labels', () => {
    const chips = filterChips(f({ outcome: 'partly_allowed', judge: 'Afridi', query: '3031' }));
    expect(chips).toEqual(['Partly allowed', 'Case or party: 3031', 'Judge: Afridi']);
    expect(activeFilterCount(f({ outcome: 'allowed', judge: ' ' }))).toBe(1);
  });
});

describe('plans', () => {
  it('stored names map to the three plans', () => {
    expect(planKey('Premium')).toBe('premium');
    expect(planKey('Standard')).toBe('standard');
    expect(planKey('pro')).toBe('standard');
    expect(planKey(undefined)).toBe('free');
    expect(planKey('something else')).toBe('free');
  });

  it('limits match the server (modules/payment/plans.py)', () => {
    expect([PLANS.free.dailyLimit, PLANS.standard.dailyLimit, PLANS.premium.dailyLimit]).toEqual([2, 20, 50]);
    expect([PLANS.standard.price, PLANS.premium.price]).toEqual([10, 20]);
    expect(PLANS.free.maxResults).toBe(10);
  });

  it('Free unlocks no tool; Standard and Premium unlock them all', () => {
    expect(FEATURES.some((x) => PLANS.free.features[x])).toBe(false);
    expect(FEATURES.every((x) => PLANS.standard.features[x] && PLANS.premium.features[x])).toBe(true);
  });
});

describe('names and addresses', () => {
  it('slugs', () => {
    expect(slugify('  Bail in NAB cases: a guide!  ')).toBe('bail-in-nab-cases-a-guide');
    expect(slugifyTyping('my ')).toBe('my-');
    expect(slugify('a'.repeat(80)).length).toBeLessThanOrEqual(50);
  });

  it('chat addresses round-trip to their conversation', () => {
    const id = '298f986e-1111-2222-3333-444455556666';
    const slug = chatSlug(id, 'NAB case on bail');
    expect(chatPath(id, 'NAB case on bail')).toBe(`/chat/${slug}`);
    expect(slugMatches(slug, id)).toBe(true);
    expect(slugMatches(slug, '00000000-1111-2222-3333-444455556666')).toBe(false);
  });

  it('case names and outcomes read naturally', () => {
    expect(prettyCaseName('judgement_C_A_42-K_2016.pdf')).toBe('C.A. 42-K 2016');
    expect(prettyOutcome('partly_allowed')).toBe('Partly allowed');
    expect(prettyOutcome('unknown')).toBe('');
    expect(caseJudges({ bench: 'Justice A' })).toEqual(['Justice A']);
    expect(caseJudges({})).toEqual([]);
  });

  it('an answer saying there is no authority counts as empty', () => {
    expect(isEmptyAnswer(`${NO_AUTHORITY_MARKER} nothing here`)).toBe(true);
  });
});
