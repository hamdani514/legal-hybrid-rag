import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * Step-by-step guide to using the research workspace, from creating an
 * account to keeping a research history. Every control named here is named
 * exactly as it appears in the app, so a reader can follow along on screen.
 *
 * The query tips come from the retrieval tests (14,385 queries over 2,877
 * judgments): queries that named the parties, the statute, the place or the
 * figures found their judgment far more often than
 * vague one-line descriptions.
 */
const STEPS = [
  {
    icon: 'person_add',
    title: 'Create your account',
    body: 'Sign up with your Gmail address, or continue with Google. We email you a 6-digit code to verify the address, and your account is ready.',
    points: ['Free for law students', 'Sign in once, stay signed in'],
  },
  {
    icon: 'balance',
    title: 'Open the Research Workspace',
    body: 'After signing in you land in the workspace. You can always return to it from Research Workspace in your profile menu. Press New Research Query to start a fresh conversation.',
    points: ['One conversation per matter', 'Your history stays in the sidebar'],
  },
  {
    icon: 'edit_note',
    title: 'Describe your case or ask a question',
    body: 'Write in plain words: what happened, what each side claims, and what the courts decided so far. A short legal question works too. Press Enter for a new line and Ctrl + Enter to send.',
    points: ['Free plan: 1 search a day', 'Standard plan: 20 searches a day'],
  },
  {
    icon: 'gavel',
    title: 'Read the matching judgments',
    body: 'Up to ten judgments come back, best match first. The top one is analysed for you; press Analyse this case for any other, or Summary for a three-line overview of the parties, the problem and the outcome.',
    points: ['Strong match', 'Possible match — verify', 'Related case'],
  },
  {
    icon: 'travel_explore',
    title: 'Go further',
    body: 'Press More relevant cases to load the next ten. Filter the list, Compare judgments side by side, Download PDF to read the full judgment, or Copy a case and its analysis to share.',
    points: ['Up to 100 cases per search', 'Matched sections shown on each case'],
  },
  {
    icon: 'history',
    title: 'Keep your research',
    body: 'Every conversation is saved under Research History. Open the ⋯ menu beside one to Rename, Pin it to the top, or Delete it, and reopen any conversation later from any device.',
    points: ['Pinned conversations stay on top', 'Saved to your account'],
  },
];

const GOOD_QUERIES = [
  {
    query: 'NAB case on bail under the NAB Ordinance',
    why: 'The topic and the statute',
  },
  {
    query: 'Pre-emption suit dismissed because talb-i-muwathibat was not proved',
    why: 'The legal issue in the Court’s own terms',
  },
  {
    query: 'Postmaster dismissed for misappropriating government funds; tribunal changed it to compulsory retirement',
    why: 'Who, what happened, and what each forum decided',
  },
  {
    query: 'Daughters sued their brother over a gift mutation of their father’s land, sanctioned after his death',
    why: 'The parties, the transaction and what went wrong',
  },
];

const TIPS = [
  'Name the parties, the statute or section, the place and any figures you know.',
  'Keep to one legal issue per search; start a new query for the next one.',
  'A result marked Possible match — verify is related, not confirmed: read it before relying on it.',
  'If nothing fits, add a detail the judgment would contain rather than repeating the same words.',
];

const UsageGuide = () => (
  <section id="guide" aria-labelledby="guide-title" className="ground-tint w-full scroll-mt-24 px-5 py-12 sm:px-8 md:py-16">
    <div className="mx-auto max-w-[1200px]">
      <SectionOpener
        eyebrow="Step-by-step guide"
        icon="menu_book"
        title={<span id="guide-title">How to use</span>}
        accent="Verdict AI"
        lede="From your first sign-in to a saved, shareable line of authority — six steps, with every button named as you will see it."
        className="mx-auto"
      />

      {/* Steps */}
      <ol className="mt-10 grid grid-cols-1 gap-6 md:mt-12 md:grid-cols-2 lg:grid-cols-3">
        {STEPS.map(({ icon, title, body, points }, index) => (
          <Reveal
            as="li"
            key={title}
            delay={index * 80}
            className="relative flex h-full flex-col rounded-3xl border border-ash-200 bg-white p-7 shadow-soft transition-all duration-300 hover:-translate-y-1 border-trace hover:border-brand-100 hover:shadow-card"
          >
            <div className="flex items-center gap-3">
              <span className="grad-brand flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-[14px] font-bold text-white shadow-glow">
                {index + 1}
              </span>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-brand-600">
                <span className="material-symbols-outlined text-[19px]" aria-hidden="true">
                  {icon}
                </span>
              </span>
            </div>

            <h3 className="mt-5 font-display text-[17px] font-bold leading-snug tracking-[-0.01em] text-ash-900">
              {title}
            </h3>
            <p className="mt-2.5 flex-1 font-prose text-[14px] leading-[1.7] text-ash-600">{body}</p>

            <ul className="mt-5 flex flex-wrap gap-2">
              {points.map((point) => (
                <li
                  key={point}
                  className="rounded-full border border-ash-200 bg-ash-50 px-3 py-1 font-ui text-[11.5px] font-semibold text-ash-600"
                >
                  {point}
                </li>
              ))}
            </ul>
          </Reveal>
        ))}
      </ol>

      {/* Writing a good query */}
      <Reveal delay={200} className="mt-10">
        <div className="border-trace grid grid-cols-1 gap-8 rounded-3xl border border-ash-200 bg-white p-7 shadow-soft sm:p-9 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <div className="flex items-center gap-2.5">
              <span className="material-symbols-outlined text-[22px] text-brand-600" aria-hidden="true">
                tips_and_updates
              </span>
              <h3 className="font-display text-[17px] font-bold text-ash-900">Queries that find the judgment</h3>
            </div>
            <ul className="mt-5 flex flex-col gap-3">
              {GOOD_QUERIES.map(({ query, why }) => (
                <li key={query} className="rounded-2xl border border-ash-200 bg-ash-50/70 px-4 py-3">
                  <p className="font-prose text-[14px] font-medium text-ash-900">&ldquo;{query}&rdquo;</p>
                  <p className="mt-1 font-ui text-[12px] font-semibold text-brand-700">{why}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="lg:col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="material-symbols-outlined text-[22px] text-emerald-600" aria-hidden="true">
                checklist
              </span>
              <h3 className="font-display text-[17px] font-bold text-ash-900">Get better results</h3>
            </div>
            <ul className="mt-5 flex flex-col gap-3.5">
              {TIPS.map((tip) => (
                <li key={tip} className="flex gap-2.5 font-prose text-[14px] leading-[1.65] text-ash-600">
                  <span className="material-symbols-outlined mt-0.5 shrink-0 text-[17px] text-emerald-600" aria-hidden="true">
                    check_circle
                  </span>
                  {tip}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Reveal>
    </div>
  </section>
);

export default UsageGuide;
