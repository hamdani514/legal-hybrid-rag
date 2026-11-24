import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

// The plan store subscribes to the browser; a server render needs a plain plan.
vi.mock('../user/lib/plan', async (original) => ({
  ...(await original()),
  usePlan: () => ({
    key: 'premium',
    features: { analyse: true, summarize: true, compare: true, download: true, filter: true, see_all: true, copy: true },
  }),
}));
import { MemoryRouter } from 'react-router-dom';
import ResultsPanel from '../user/components/ResultsPanel';
import { markFresh } from '../lib/typing';

const cite = (id, extra = {}) => ({
  judgment_id: id,
  filename: `judgement_Crl_P_${id}.pdf`,
  similarity_score: 0.9,
  confidence: 'related',
  sections_retrieved: ['FACTS'],
  answer_status: 'on_demand',
  card: {
    case_display: `Criminal Petition No. ${id}`,
    appellant: 'A',
    respondent: 'B',
    headnote: 'The petitioner sought pre-arrest bail. The Court granted it.',
    sections: ['Section 377 PPC'],
    sections_source: 'summary',
  },
  ...extra,
});

const reply = () => ({
  sender: 'ai',
  query: 'pre arrest bail in 377',
  notice: 'Showing results for "pre arrest bail in 377".',
  text: '',
  citations: [cite('1'), cite('2'), cite('3', { answer_status: 'ready', llm_answer: '[RELEVANT FACTS]\nFacts.\n[FINAL DECISION]\nDismissed.' })],
});

const render = (message) =>
  renderToString(
    <MemoryRouter>
      <ResultsPanel message={message} />
    </MemoryRouter>,
  );

describe('results panel renders (smoke)', () => {
  it('a reopened reply shows everything at once', () => {
    const html = render(reply());
    expect(html).toContain('Criminal Petition No. 1');
    expect(html).toContain('Criminal Petition No. 2');
    expect(html).toContain('The petitioner sought pre-arrest bail');
    // Case 3 came already analysed: its analysis, not its card.
    expect(html).toContain('Facts.');
    expect(html).toContain('Dismissed.');
    // The tools at the bottom are there too.
    expect(html).toContain('Compare');
  });

  it('a new reply starts empty below the top: cases appear in turn', () => {
    const html = render(markFresh(reply()));
    // At the first instant: no case, no empty box, no tools yet.
    expect(html).not.toContain('Criminal Petition No. 1');
    expect(html).not.toContain('Criminal Petition No. 2');
    expect(html).not.toContain('Dismissed.');
    expect(html).not.toContain('Compare');
  });

  it('a new reply whose writing has finished shows all of it (nothing stays hidden)', () => {
    const html = render(markFresh(reply(), performance.now() - 120000));
    expect(html).toContain('Criminal Petition No. 2');
    expect(html).toContain('Dismissed.');
    expect(html).toContain('Compare');
  });
});
