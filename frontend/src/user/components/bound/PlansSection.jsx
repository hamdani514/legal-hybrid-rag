import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

const PLANS = [
  {
    name: 'Student',
    price: 'Free',
    cadence: 'for verified students',
    summary: 'Enough to carry a moot, a seminar paper or a dissertation chapter.',
    features: [
      '25 research sessions each month',
      'Full text of every judgment',
      'Division-level navigation',
      'Export with citation',
    ],
    cta: 'Verify enrolment',
    to: '/signup',
    emphasis: false,
  },
  {
    name: 'Advocate',
    price: 'Rs 2,400',
    cadence: 'per month',
    summary: 'For practitioners researching against a filing deadline.',
    features: [
      'Unlimited research sessions',
      'Side-by-side comparison',
      'Saved research trails',
      'Priority retrieval queue',
      'Support within one working day',
    ],
    cta: 'Get started',
    to: '/signup',
    emphasis: true,
  },
  {
    name: 'Chambers',
    price: 'On request',
    cadence: 'per seat, billed annually',
    summary: 'Shared archives and seat management for a firm or set of chambers.',
    features: [
      'Everything in Advocate',
      'Shared research trails',
      'Private document ingestion',
      'Named account contact',
    ],
    cta: 'Talk to us',
    to: '/contact',
    emphasis: false,
  },
];

/**
 * Pricing. The middle tier carries the gradient fill and lifts slightly, so
 * the recommendation reads without a badge shouting about it.
 */
const PlansSection = () => {
  return (
    <section aria-labelledby="plans-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Pricing"
          icon="sell"
          title={<span id="plans-title">Students research free.</span>}
          accent="Practitioners pay for throughput."
          lede="No card required to start, and no tier that hides your own research behind an upgrade."
          className="mx-auto"
        />

        <div className="mt-14 grid grid-cols-1 gap-5 md:mt-20 lg:grid-cols-3">
          {PLANS.map(({ name, price, cadence, summary, features, cta, to, emphasis }, index) => (
            <Reveal
              key={name}
              delay={index * 110}
              className={`lift-card relative flex flex-col rounded-4xl p-8 sm:p-9 ${
                emphasis
                  ? 'grad-brand text-white shadow-glow-lg lg:-my-4'
                  : 'border border-ash-200 bg-white shadow-soft hover:border-brand-200 hover:shadow-card'
              }`}
            >
              {emphasis && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-white px-4 py-1 font-ui text-[11px] font-bold uppercase tracking-[0.1em] text-brand-800 shadow-card">
                  Most popular
                </span>
              )}

              <h3
                className={`font-display text-[15px] font-bold tracking-[-0.01em] ${
                  emphasis ? 'text-brand-100' : 'text-brand-700'
                }`}
              >
                {name}
              </h3>

              <p className="mt-5 flex flex-wrap items-baseline gap-2">
                <span
                  className={`font-display text-[2.75rem] font-bold leading-none tracking-[-0.035em] ${
                    emphasis ? 'text-white' : 'text-ash-900'
                  }`}
                >
                  {price}
                </span>
                <span
                  className={`font-prose text-[13px] ${emphasis ? 'text-white/70' : 'text-ash-500'}`}
                >
                  {cadence}
                </span>
              </p>

              <p
                className={`mt-4 font-prose text-[14.5px] leading-[1.7] ${
                  emphasis ? 'text-white/85' : 'text-ash-600'
                }`}
              >
                {summary}
              </p>

              <ul className="mt-8 flex flex-1 flex-col gap-3.5">
                {features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <span
                      aria-hidden="true"
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                        emphasis ? 'bg-white/20 text-white' : 'bg-mint-400/20 text-mint-700'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[13px]">check</span>
                    </span>
                    <span
                      className={`font-prose text-[14px] leading-[1.6] ${
                        emphasis ? 'text-white/90' : 'text-ash-700'
                      }`}
                    >
                      {feature}
                    </span>
                  </li>
                ))}
              </ul>

              <Link
                to={to}
                className={`mt-9 inline-flex items-center justify-center rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold transition-all duration-300 ${
                  emphasis
                    ? 'bg-white text-brand-800 hover:-translate-y-0.5 hover:shadow-card-lg'
                    : 'border border-ash-300 text-ash-800 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                }`}
              >
                {cta}
              </Link>
            </Reveal>
          ))}
        </div>

        <Reveal
          as="p"
          variant="fade"
          delay={200}
          className="mx-auto mt-9 max-w-[40rem] text-center font-prose text-[13px] leading-6 text-ash-500"
        >
          Prices in Pakistani rupees, exclusive of applicable tax. Student verification is by
          institutional email.
        </Reveal>
      </div>
    </section>
  );
};

export default PlansSection;
