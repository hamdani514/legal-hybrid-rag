import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * Every feature the research workspace gives a user, in three groups: finding
 * the right judgment, understanding it, and working with it.
 *
 * Each card shows the control exactly as it is labelled in the app (`control`)
 * so a reader recognises it on screen, and describes only what the feature
 * really does — the compare fields are the comparator's own FIELDS, the filter
 * options are ResultsFilter's, the summary lines are answerFormat's.
 */
const GROUPS = [
  {
    key: 'find',
    label: 'Find the right judgment',
    icon: 'search',
    tone: 'text-sky-600 bg-sky-50 border-sky-100',
    features: [
      {
        icon: 'edit_note',
        control: 'Describe your case',
        title: 'Search in plain words',
        body: 'Describe what happened, what each side claims and what the courts decided — or ask a short legal question. The search reads meaning, not just matching words.',
      },
      {
        icon: 'verified',
        control: 'Strong match',
        title: 'Know how close each result is',
        body: 'Every result is labelled Strong match, Possible match — verify, or Related case, and shows the sections of the judgment your search matched.',
      },
      {
        icon: 'expand_more',
        control: 'More relevant cases',
        title: 'See every relevant judgment',
        body: 'Ten judgments come back first. Press More relevant cases for the next ten, up to a hundred — only cases that still match your search are added.',
      },
    ],
  },
  {
    key: 'understand',
    label: 'Understand it quickly',
    icon: 'lightbulb',
    tone: 'text-emerald-600 bg-emerald-50 border-emerald-100',
    features: [
      {
        icon: 'auto_awesome',
        control: 'Analyse this case',
        title: 'An analysis against your facts',
        body: 'The top judgment is analysed automatically; any other on request. The analysis sets out what the Court held and how it fits your situation, including where it differs.',
      },
      {
        icon: 'summarize',
        control: 'Summary',
        title: 'Any judgment in three lines',
        body: 'Parties, legal problem and decision at a glance — opened instantly, before you decide whether the full judgment is worth reading.',
      },
      {
        icon: 'library_books',
        control: 'See all judgments',
        title: 'The whole list in one view',
        body: 'Every judgment the search returned, in one panel, with its match label, the sections matched and a download button beside each.',
      },
      {
        icon: 'document_scanner',
        control: 'Scanned judgments',
        title: 'Old and scanned judgments included',
        body: 'Paper judgments are straightened, read by OCR and indexed like typed ones, so a scanned decision is found and analysed the same way.',
      },
    ],
  },
  {
    key: 'use',
    label: 'Work with your authorities',
    icon: 'work',
    tone: 'text-indigo-600 bg-indigo-50 border-indigo-100',
    features: [
      {
        icon: 'filter_list',
        control: 'Filter',
        title: 'Narrow the list',
        body: 'By final decision, by date decided, by case number or party, or by judge — any combination, and the original list is one click away.',
      },
      {
        icon: 'compare_arrows',
        control: 'Compare judgments',
        title: 'Set authorities side by side',
        body: 'Up to ten judgments in one table: case number, date, bench, parties, subject, key facts, legal issue, the Court’s reasoning and the final decision.',
      },
      {
        icon: 'download',
        control: 'Download PDF',
        title: 'Take the original judgment',
        body: 'Download the full judgment exactly as reported, for your file, a brief or a court bundle.',
      },
      {
        icon: 'content_copy',
        control: 'Copy',
        title: 'Share a case or the whole answer',
        body: 'Copy one case with its analysis, or every judgment in the answer at once, ready to paste into a memo, an email or a chat.',
      },
      {
        icon: 'history',
        control: 'Research History',
        title: 'Keep every line of research',
        body: 'Each conversation is saved to your account. Rename it, pin it to the top, or delete it, and reopen it from any device.',
      },
    ],
  },
];

const ControlChip = ({ icon, label }) => (
  <span className="inline-flex items-center gap-1.5 rounded-full border border-ash-300 bg-white px-3 py-1 font-ui text-[12px] font-semibold text-ash-700 shadow-2xs">
    <span className="material-symbols-outlined text-[15px] text-brand-600" aria-hidden="true">
      {icon}
    </span>
    {label}
  </span>
);

const FeatureShowcase = () => (
  <section id="features" aria-labelledby="features-title" className="w-full scroll-mt-24 bg-white px-5 py-12 sm:px-8 md:py-16">
    <div className="mx-auto max-w-[1200px]">
      <SectionOpener
        eyebrow="Features"
        icon="widgets"
        title={<span id="features-title">Everything you can do</span>}
        accent="with a judgment"
        lede="From the first search to the authority in your brief: analyse a case against your facts, filter and compare the results, and download the judgment itself."
        className="mx-auto"
      />

      <div className="mt-10 flex flex-col gap-10 md:mt-12">
        {GROUPS.map(({ key, label, icon, tone, features }) => (
          <div key={key}>
            <Reveal className="flex items-center gap-3">
              <span className={`flex h-9 w-9 items-center justify-center rounded-xl border ${tone}`}>
                <span className="material-symbols-outlined text-[19px]" aria-hidden="true">
                  {icon}
                </span>
              </span>
              <h3 className="font-display text-[19px] font-bold tracking-[-0.015em] text-ash-900">{label}</h3>
              <span aria-hidden="true" className="ml-2 h-px flex-1 bg-ash-200" />
            </Reveal>

            <ul className={`mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 ${features.length === 4 ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}`}>
              {features.map(({ icon: fIcon, control, title, body }, index) => (
                <Reveal
                  as="li"
                  key={title}
                  delay={index * 70}
                  className="group flex h-full flex-col rounded-3xl border border-ash-200 bg-white p-6 shadow-soft transition-all duration-300 hover:-translate-y-1 border-trace hover:border-brand-100 hover:shadow-card"
                >
                  <ControlChip icon={fIcon} label={control} />
                  <h4 className="mt-5 font-display text-[16px] font-bold leading-snug tracking-[-0.01em] text-ash-900">
                    {title}
                  </h4>
                  <p className="mt-2 font-prose text-[13.5px] leading-[1.7] text-ash-600">{body}</p>
                </Reveal>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  </section>
);

export default FeatureShowcase;
