import Reveal from '../Reveal';

/**
 * The credibility beat under the hero: four statements about how the archive
 * behaves, each one something the system actually does. Kept quiet, on a
 * tinted band, with no competing call to action.
 */
const ASSURANCES = [
  {
    icon: 'account_tree',
    title: 'Structured, not scraped',
    note: 'Each judgment is split into its six working parts before indexing.',
  },
  {
    icon: 'format_quote',
    title: 'Answers carry citations',
    note: 'Every finding names the judgment and its appeal number.',
  },
  {
    icon: 'rule',
    title: 'It declines to guess',
    note: 'Where the reasoning is not in the record, it says so.',
  },
  {
    icon: 'lock',
    title: 'Your research stays yours',
    note: 'Queries are never used to train the underlying model.',
  },
];

const AuthorityStrip = () => {
  return (
    <section
      aria-label="How the archive behaves"
      className="ground-tint w-full border-y border-ash-200 px-5 py-16 sm:px-8 sm:py-20"
    >
      <ul className="mx-auto grid max-w-[1200px] grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {ASSURANCES.map(({ icon, title, note }, index) => (
          <Reveal
            as="li"
            key={title}
            delay={index * 80}
            className="lift-card group flex flex-col rounded-3xl border border-ash-200 bg-white p-6 shadow-soft hover:border-brand-200 hover:shadow-card"
          >
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-100"
            >
              <span className="material-symbols-outlined text-[21px]">{icon}</span>
            </span>

            <h3 className="mt-5 font-display text-[16px] font-bold tracking-[-0.01em] text-ash-900">
              {title}
            </h3>

            <p className="mt-2.5 font-prose text-[14px] leading-[1.68] text-ash-600">{note}</p>
          </Reveal>
        ))}
      </ul>
    </section>
  );
};

export default AuthorityStrip;
