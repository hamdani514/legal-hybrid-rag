import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';
import CardBubbles from './CardBubbles';
import { startCheckout } from '../../lib/payments';

const PLANS = [
  {
    name: 'Free',
    price: 'Free',
    cadence: 'no card required',
    summary: 'Enough to carry a moot, a seminar paper or a dissertation chapter.',
    features: [
      '25 research sessions each month',
      'Full text of every judgment',
      'Division-level navigation',
      'Export with citation',
    ],
    cta: 'Create account',
    to: '/signup',
    emphasis: false,
  },
  {
    name: 'Standard',
    price: '$10',
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
    checkout: true,
  },
  {
    name: 'Premium',
    price: 'On request',
    cadence: 'per seat, billed annually',
    summary: 'Shared archives and seat management for a firm or set of chambers.',
    features: [
      'Everything in Standard',
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
 * Pricing. Individual hover animation:
 * - Hover on Left: Left card slides/tilts outward, others stay in place.
 * - Hover on Middle: Middle card zooms/scales up, others stay in place.
 * - Hover on Right: Right card slides/tilts outward, others stay in place.
 */
const PlansSection = () => {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [payError, setPayError] = useState('');

  // The paid plan leaves for Stripe's hosted page; everything else is a link.
  const onSubscribe = async () => {
    if (busy) return;
    setPayError('');
    setBusy(true);
    const result = await startCheckout();
    if (!result.ok) {
      setBusy(false);
      if (result.reason === 'signin') {
        navigate('/login', { state: { next: '/pricing' } });
        return;
      }
      setPayError(result.message);
    }
    // On success the browser is already on its way to Stripe.
  };

  return (
    <section aria-labelledby="plans-title" className="w-full px-5 py-20 sm:px-8 md:py-28 overflow-x-hidden">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Pricing"
          icon="sell"
          title={<span id="plans-title">Students research free.</span>}
          accent="Practitioners pay for throughput."
          lede="No card required to start, and no tier that hides your own research behind an upgrade."
          className="mx-auto"
        />

        {/* Pricing Cards */}
        <div className="pricing-deck relative mx-auto mt-14 max-w-[1140px] md:mt-20 lg:py-10">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 lg:gap-3 items-stretch">
            {PLANS.map(({ name, price, cadence, summary, features, cta, to, emphasis, checkout }, index) => {
              const cardPositionClass =
                index === 0
                  ? 'pricing-card-left'
                  : index === 1
                  ? 'pricing-card-center'
                  : 'pricing-card-right';

              return (
                <div
                  key={name}
                  className={`pricing-card ${cardPositionClass} relative flex flex-col justify-between overflow-hidden rounded-4xl p-8 sm:p-9 ${
                    emphasis
                      ? 'bg-gradient-to-br from-[#0066f6] via-[#004ecc] to-[#1f00db] text-white shadow-glow-lg'
                      : 'border border-ash-200 bg-white shadow-soft hover:border-brand-200'
                  }`}
                >
                  {/* Floating randomly moving bubbles */}
                  <CardBubbles tone={emphasis ? 'light' : 'dark'} density="compact" />

                  <div className="relative z-[2]">
                    {emphasis && (
                      <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 rounded-full bg-white px-4 py-1 font-ui text-[11px] font-bold uppercase tracking-[0.1em] text-brand-800 shadow-card">
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
                        className={`font-prose text-[13px] ${
                          emphasis ? 'text-white/70' : 'text-ash-500'
                        }`}
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

                    <ul className="mt-8 flex flex-col gap-3.5">
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
                  </div>

                  {checkout ? (
                    <button
                      type="button"
                      onClick={onSubscribe}
                      disabled={busy}
                      className={`relative z-[2] mt-9 inline-flex items-center justify-center rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-70 ${
                        emphasis
                          ? 'bg-white text-brand-800 hover:-translate-y-0.5 hover:shadow-card-lg'
                          : 'border border-ash-300 text-ash-800 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                      }`}
                    >
                      {busy ? 'Opening secure checkout…' : cta}
                    </button>
                  ) : (
                    <Link
                      to={to}
                      className={`relative z-[2] mt-9 inline-flex items-center justify-center rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold transition-all duration-300 ${
                        emphasis
                          ? 'bg-white text-brand-800 hover:-translate-y-0.5 hover:shadow-card-lg'
                          : 'border border-ash-300 text-ash-800 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                      }`}
                    >
                      {cta}
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {payError && (
          <p
            role="alert"
            className="mx-auto mt-8 max-w-[40rem] rounded-2xl border border-amber-400/40 bg-amber-400/10 px-5 py-3 text-center font-prose text-[13.5px] leading-6 text-ash-800"
          >
            {payError}
          </p>
        )}

        <Reveal
          as="p"
          variant="fade"
          delay={200}
          className="mx-auto mt-9 max-w-[40rem] text-center font-prose text-[13px] leading-6 text-ash-500"
        >
          Billed in US dollars, exclusive of applicable tax. Premium is arranged with us
          directly.
        </Reveal>
      </div>
    </section>
  );
};

export default PlansSection;
