import Reveal from '../Reveal';
import ContactForm from '../ContactForm';

/**
 * The contact spread: the enquiry form beside the direct routes, each with the
 * response time attached so a reader knows what to expect before writing.
 */
const CHANNELS = [
  {
    icon: 'school',
    label: 'Student verification',
    body: 'Write from your institutional address and enrolment is confirmed on the same account.',
    meta: 'Usually one working day',
  },
  {
    icon: 'gavel',
    label: 'Chambers & firms',
    body: 'Seat counts, shared research trails and private ingestion for your own case papers.',
    meta: 'Two working days',
  },
  {
    icon: 'bug_report',
    label: 'A wrong or missing citation',
    body: 'Send the appeal number and the passage. Retrieval faults are treated as defects, not feedback.',
    meta: 'Triaged the same day',
  },
];

const ContactPanel = () => {
  return (
    <section aria-labelledby="contact-panel-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 lg:grid-cols-[1fr_23rem] lg:gap-12">
        {/* ── The enquiry form ───────────────────────────────────────── */}
        <div>
          <Reveal variant="fade">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700">
              <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
                mail
              </span>
              Send an enquiry
            </span>
          </Reveal>

          <Reveal
            as="h2"
            delay={80}
            id="contact-panel-title"
            className="mt-6 font-display text-[clamp(1.75rem,4vw,2.5rem)] font-bold leading-[1.12] tracking-[-0.028em] text-ash-900"
          >
            Put it in <span className="grad-text">writing</span>
          </Reveal>

          <Reveal
            as="p"
            delay={150}
            className="mt-4 max-w-[40rem] font-prose text-[1.0625rem] leading-[1.75] text-ash-600"
          >
            Every enquiry reaches a person, not a queue. Include an appeal number if your question
            concerns a particular judgment.
          </Reveal>

          <div className="mt-9">
            <ContactForm />
          </div>
        </div>

        {/* ── Direct routes ──────────────────────────────────────────── */}
        <aside className="self-start lg:sticky lg:top-28">
          <Reveal as="h2" variant="fade" className="font-display text-[15px] font-bold text-ash-900">
            Or write directly
          </Reveal>

          <ul className="mt-5 flex flex-col gap-4">
            {CHANNELS.map(({ icon, label, body, meta }, index) => (
              <Reveal
                as="li"
                key={label}
                delay={index * 90}
                className="lift-card group rounded-3xl border border-ash-200 bg-white p-6 shadow-soft hover:border-brand-200 hover:shadow-card"
              >
                <span className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
                  >
                    <span className="material-symbols-outlined text-[19px]">{icon}</span>
                  </span>
                  <span className="font-display text-[14.5px] font-bold tracking-[-0.01em] text-ash-900">
                    {label}
                  </span>
                </span>

                <p className="mt-3.5 font-prose text-[13.5px] leading-[1.68] text-ash-600">
                  {body}
                </p>

                <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-ash-100 px-3 py-1 font-ui text-[11.5px] font-semibold text-ash-600">
                  <span aria-hidden="true" className="material-symbols-outlined text-[13px]">
                    schedule
                  </span>
                  {meta}
                </span>
              </Reveal>
            ))}
          </ul>

          <Reveal
            delay={280}
            className="mt-6 rounded-3xl border border-amber-400/40 bg-amber-400/10 p-6"
          >
            <span className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px] text-amber-500"
              >
                info
              </span>
              <span className="font-display text-[13.5px] font-bold text-ash-900">Please note</span>
            </span>
            <p className="mt-3 font-prose text-[13.5px] leading-[1.7] text-ash-700">
              We cannot advise on your matter, review your draft, or tell you how a court is likely
              to decide. For that, instruct an advocate.
            </p>
          </Reveal>
        </aside>
      </div>
    </section>
  );
};

export default ContactPanel;
