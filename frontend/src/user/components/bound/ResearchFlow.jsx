import Reveal from '../Reveal';
import SplitFeature from './SplitFeature';

/**
 * Two alternating rows that carry the argument the method cards state in
 * shorthand: what happens to your question, and what happens to the answer.
 *
 * The desk photograph leads because it is the one that shows the work as the
 * reader recognises it — paper, a laptop, a deadline. The scales-and-reports
 * photograph closes it, because the second row is about the record.
 */
const ResearchFlow = () => {
  return (
    <section
      aria-labelledby="flow-title"
      className="w-full overflow-hidden px-5 py-20 sm:px-8 md:py-28"
    >
      <div className="mx-auto flex max-w-[1200px] flex-col gap-24 md:gap-32">
        <h2 id="flow-title" className="sr-only">
          From question to citation
        </h2>

        <SplitFeature
          media="desk"
          ratio="4 / 5"
          kicker="At your desk"
          icon="edit_note"
          title="Put the question the way you"
          accent="would ask a colleague"
          body="No boolean operators, no proximity syntax, no guessing which word a judge used in 1996. Type the legal question in plain English and the archive matches on meaning — so a query about Family Court jurisdiction reaches the judgment that decided it whether or not it shares your vocabulary."
          points={[
            {
              icon: 'psychology',
              title: 'Meaning, not string matching',
              note: 'Your question is embedded into 384 dimensions and compared against every indexed passage.',
            },
            {
              icon: 'filter_alt',
              title: 'Two passes, narrow then deep',
              note: 'The first finds the right judgments; the second finds the passages inside them.',
            },
            {
              icon: 'schedule',
              title: 'Seconds, not an afternoon',
              note: 'The eleven-reports-to-find-two problem is the one this was built to remove.',
            },
          ]}
          overlay={{
            icon: 'search',
            title: 'Asked in plain words',
            body: '“Is a claim relating to dower within the jurisdiction of a Family Court?”',
            tag: 'Answered in 1.4s',
          }}
          cta={{ to: '/welcome', label: 'Open the workspace' }}
        />

        <SplitFeature
          media="scales"
          ratio="4 / 5"
          flip
          kicker="Against the record"
          icon="balance"
          title="Weighed against what the Court"
          accent="actually held"
          body="An answer is only worth the authority behind it. Every passage returned is tied to its judgment and its appeal number, the disposition travels with it, and where the record simply does not answer your question the tool says so instead of composing something that sounds right."
          points={[
            {
              icon: 'format_quote',
              title: 'The appeal number travels with the passage',
              note: 'Nothing is reported that cannot be attributed to a judgment in the index.',
            },
            {
              icon: 'rule',
              title: 'Silence where the record is silent',
              note: 'A convincing answer the Court never gave is worse than no answer at all.',
            },
            {
              icon: 'menu_book',
              title: 'A route to the report, not a substitute',
              note: 'Verify against the reported judgment before you rely on it in a filing.',
            },
          ]}
          overlay={{
            icon: 'gavel',
            title: 'Civil Appeal No. 23-P of 2017',
            body: '“…in no way can be termed as a matter relating to dower.”',
            tag: 'Appeal dismissed',
          }}
          cta={{ to: '/about', label: 'Read the method in full' }}
        />
      </div>

      {/* The disclaimer belongs beside the claim, not buried in the footer. */}
      <Reveal
        variant="fade"
        delay={120}
        className="mx-auto mt-20 max-w-[46rem] rounded-3xl border border-ash-200 bg-ash-50 px-6 py-5 text-center md:mt-24"
      >
        <p className="font-prose text-[13px] leading-[1.7] text-ash-500">
          <span
            aria-hidden="true"
            className="material-symbols-outlined mr-1.5 align-[-4px] text-[17px] text-ash-400"
          >
            info
          </span>
          A research aid, not legal advice. Applying a holding to your facts is a matter for an
          advocate.
        </p>
      </Reveal>
    </section>
  );
};

export default ResearchFlow;
