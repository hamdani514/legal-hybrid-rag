import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * The commitments the tool is held to. Each one is falsifiable rather than a
 * slogan, so a reader can check whether the product keeps them.
 */
const PRINCIPLES = [
  {
    icon: 'format_quote',
    title: 'The authority is always named',
    body: 'No finding is reported without the judgment it came from. If a passage cannot be attributed, it does not appear.',
  },
  {
    icon: 'rule',
    title: 'Silence over invention',
    body: 'Where the record does not answer a question, the tool says so. A convincing answer the Court never gave is worse than none.',
  },
  {
    icon: 'menu_book',
    title: 'The original governs',
    body: 'Everything here is a route to the reported judgment, never a replacement for it. Verify before you rely.',
  },
  {
    icon: 'account_tree',
    title: 'Structure over ranking tricks',
    body: 'Relevance comes from dividing the judgment properly, not from weighting keywords until results look plausible.',
  },
  {
    icon: 'lock',
    title: 'Your research is private',
    body: 'Queries and saved trails are yours. They are not used to train the underlying model, and not sold.',
  },
  {
    icon: 'balance',
    title: 'It will not advise you',
    body: 'It reports what the Court has held. Applying that to your facts is a matter for an advocate, not a model.',
  },
];

const PrincipleList = () => {
  return (
    <section
      aria-labelledby="principles-title"
      className="ground-tint w-full border-y border-ash-200 px-5 py-20 sm:px-8 md:py-28"
    >
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Our commitments"
          icon="verified"
          title={<span id="principles-title">What this tool will and</span>}
          accent="will not do"
          lede="Legal research carries consequences. These are the rules the system is built to, stated plainly enough to be held against it."
          className="mx-auto"
        />

        <ul className="mt-14 grid grid-cols-1 gap-5 md:mt-20 sm:grid-cols-2 lg:grid-cols-3">
          {PRINCIPLES.map(({ icon, title, body }, index) => (
            <Reveal
              as="li"
              key={title}
              delay={index * 70}
              className="lift-card group flex flex-col rounded-3xl border border-ash-200 bg-white p-7 shadow-soft hover:border-brand-200 hover:shadow-card"
            >
              <span
                aria-hidden="true"
                className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
              >
                <span className="material-symbols-outlined text-[21px]">{icon}</span>
              </span>

              <h3 className="mt-5 font-display text-[17px] font-bold leading-snug tracking-[-0.015em] text-ash-900">
                {title}
              </h3>

              <p className="mt-3 font-prose text-[14px] leading-[1.7] text-ash-600">{body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
};

export default PrincipleList;
