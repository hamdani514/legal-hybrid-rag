// The rules that decide what a user sees: which cases a filter keeps, what a
// plan unlocks, how a case is named and how chat addresses are built.
// Run with `npm test`; the Docker build runs them too, so a failure stops it.
import { describe, expect, it } from 'vitest';
import { EMPTY_FILTERS, activeFilterCount, caseDate, matchesFilters, matchesSections } from '../user/lib/filters';
import { filterChips } from '../user/lib/filterSummary';
import { FEATURES, PLANS, planKey } from '../user/lib/plan';
import { slugify, slugifyTyping } from '../lib/slug';
import { retryWhileRestarting } from '../lib/api';
import { chatPath, chatSlug, slugMatches } from '../user/lib/chatSlug';
import {
  caseJudges, caseSummaryLines, isEmptyAnswer, meaningfulSections, offPointReason, prettyCaseName, prettyOutcome,
  NO_AUTHORITY_MARKER,
} from '../user/lib/answerFormat';

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
    expect(filterChips(f({ section: '302 PPC' }))).toEqual(['Section: 302 PPC']);
    expect(activeFilterCount(f({ section: '302' }))).toBe(1);
  });
});

describe('analysis of a judgment that does not address the question', () => {
  const offPoint = [
    '[NO RELEVANT AUTHORITY]',
    'Why: The query concerns pre-arrest bail under Section 377 PPC; this judgment decides a conviction appeal.',
    '[RELEVANT FACTS]', 'The appellant was convicted of murder and sodomy.',
    '[FINAL DECISION]', 'In this judgment, the appeal was dismissed.',
    '[FIT WITH YOUR SITUATION]', 'Distinguishable: it is not a bail matter.',
  ].join('\n');

  it('is shown as an analysis with its reason, not as empty', () => {
    expect(isEmptyAnswer(offPoint)).toBe(false);
    expect(offPointReason(offPoint)).toBe(
      'The query concerns pre-arrest bail under Section 377 PPC; this judgment decides a conviction appeal.');
    expect(meaningfulSections(offPoint).map((s) => s.heading)).toEqual(['RELEVANT FACTS', 'FINAL DECISION']);
  });

  it('the marker alone is still empty, and an on-point analysis has no reason', () => {
    const bare = '[NO RELEVANT AUTHORITY]\nThe retrieved judgments do not address this query.';
    expect(isEmptyAnswer(bare)).toBe(true);
    expect(offPointReason(bare)).toBe(null);
    expect(offPointReason('[RELEVANT FACTS]\nBail was refused.')).toBe(null);
  });
});

// The same card and inputs as the server's self-test (app/retrieval/case_sections.py),
// so the browser and the server agree on what a Section filter keeps.
describe('section filter', () => {
  const card = {
    provisions: ['Article 185(3)', 'Section 302(b) PPC', 'Section 34 PPC', 'Section 342 CrPC',
                 'Section 497(2) CrPC', 'Section 489-F PPC'],
  };
  const withCard = { ...cite, card: { ...cite.card, ...card } };

  it('keeps a case for every way of writing a section it involves', () => {
    for (const t of ['302', 'section 302', 's. 302 PPC', '302(b)', '302 (b) Pakistan Penal Code', '34',
                     '302, 34', '302 and 34 PPC', '489-F', '489F', '489 F', '497(2) Cr.P.C.', 'Article 185(3)',
                     'art. 185', 'murder', '', 'u/s 302 PPC', '302 b', '302-B PPC']) {
      expect(matchesSections(card, t), t).toBe(true);
    }
  });

  it('leaves out a case that does not involve it', () => {
    for (const t of ['302(c)', '302 CrPC', '377', '302, 377', 'Article 199', '489-G', 'section 185']) {
      expect(matchesSections(card, t), t).toBe(false);
    }
  });

  it('a lettered section matches its sub-clause form, both ways', () => {
    const cnsa = { provisions: ['Section 9-C CNSA'] };
    for (const t of ['9(c) CNSA', '9-C', '9c']) expect(matchesSections(cnsa, t), t).toBe(true);
    // A lettered section is its own section: 489-F (cheque) is not 489 (currency notes).
    expect(matchesSections({ provisions: ['Section 489-F PPC'] }, '489')).toBe(false);
    expect(matchesSections(cnsa, '9(b)')).toBe(false);
  });

  it('an older spelling without the hyphen is the same lettered section', () => {
    const old = { provisions: ['Section 377B PPC'] };
    expect(matchesSections(old, '377-B')).toBe(true);
    expect(matchesSections(old, '377')).toBe(false);   // 377-B is not 377
  });

  it('works through the filter dialog, and a case with no sections is left out', () => {
    expect(matchesFilters(withCard, f({ section: '302 PPC' }))).toBe(true);
    expect(matchesFilters(withCard, f({ section: '377' }))).toBe(false);
    expect(matchesFilters(cite, f({ section: '302' }))).toBe(false);
  });

  it('the summary names the sections, and says "cited" when they are only cited', () => {
    const about = caseSummaryLines({ appellant: 'A', respondent: 'B', sections: ['Section 302(b) PPC', 'Section 34 PPC'],
                                     sections_source: 'summary' });
    expect(about).toContainEqual({ label: 'Sections', text: 'Section 302(b) PPC · Section 34 PPC' });
    const cited = caseSummaryLines({ appellant: 'A', respondent: 'B', sections: ['Section 497 CrPC'], sections_source: 'cited' });
    expect(cited).toContainEqual({ label: 'Sections cited', text: 'Section 497 CrPC' });
    expect(caseSummaryLines({ appellant: 'A', respondent: 'B' }).some((l) => l.label.startsWith('Sections'))).toBe(false);
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

describe('restarts', () => {
  const reply = (status) => ({ status });
  it('a 502 while the server restarts is retried, then the answer is returned', async () => {
    const seen = [502, 502, 200];
    let calls = 0;
    const res = await retryWhileRestarting(async () => reply(seen[calls++]), [0, 0, 0]);
    expect(res.status).toBe(200);
    expect(calls).toBe(3);
  });

  it('a refused connection is retried too', async () => {
    let calls = 0;
    const res = await retryWhileRestarting(async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('Failed to fetch');
      return reply(200);
    }, [0, 0]);
    expect(res.status).toBe(200);
  });

  it('a busy search (503, short Retry-After) is retried twice, then shown', async () => {
    const busyReply = { status: 503, headers: { get: (h) => (h === 'Retry-After' ? '0.001' : null) } };
    let calls = 0;
    const res = await retryWhileRestarting(async () => { calls += 1; return busyReply; }, [0, 0]);
    expect([res.status, calls]).toEqual([503, 3]);
    calls = 0;
    const ok = await retryWhileRestarting(async () => { calls += 1; return calls < 2 ? busyReply : reply(200); }, [0]);
    expect([ok.status, calls]).toEqual([200, 2]);
  });

  it('answers from the app itself are not retried, and retrying stops', async () => {
    let calls = 0;
    const unavailable = { status: 503, headers: { get: (h) => (h === 'Retry-After' ? '60' : null) } };
    const busy = await retryWhileRestarting(async () => { calls += 1; return unavailable; }, [0, 0]);
    expect([busy.status, calls]).toEqual([503, 1]);
    calls = 0;
    const down = await retryWhileRestarting(async () => { calls += 1; return reply(502); }, [0, 0]);
    expect([down.status, calls]).toEqual([502, 3]);
  });
});
