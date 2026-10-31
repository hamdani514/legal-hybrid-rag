import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';
import CardBubbles from './CardBubbles';
import { startCheckout } from '../../lib/payments';
import useIsLoggedIn from '../../hooks/useIsLoggedIn';
import { toast } from '../../../lib/toast';
import useToastOn from '../../../lib/useToastOn';
import { usePlan } from '../../lib/plan';

// The limits mirror backend/modules/payment/plans.py, which enforces them.
// A feature with `locked: true` is listed so Free users see what they lack.
const PLANS = [
  {
    key: 'free',
    name: 'Free',
    price: 'Free',
    cadence: 'no card required',
    summary: 'Find the judgments that match your case, each summarised in a few lines.',
    features: [
      { text: '2 research queries a day (resets 00:00 UTC)' },
      { text: 'Up to 10 relevant judgments per search' },
      { text: 'A short case summary of each judgment' },
      { text: 'Analyse, summarise and filter', locked: true },
      { text: 'Download, compare and copy', locked: true },
    ],
    cta: 'Create account',
    to: '/signup',
    emphasis: false,
  },
  {
    key: 'standard',
    name: 'Standard',
    price: '$10',
    cadence: 'per month',
    summary: 'Every research tool, for practitioners who search every day.',
    features: [
      { text: '20 research queries a day (resets 00:00 UTC)' },
      { text: 'Every relevant judgment, ten at a time' },
      { text: 'Analyse and summarise each case' },
      { text: 'Filter, compare and see all judgments' },
      { text: 'Download the PDF and copy the text' },
      { text: 'Cancel anytime — access kept until period end' },
    ],
    cta: 'Get Standard',
    emphasis: true,
    checkout: true,
  },
  {
    key: 'premium',
    name: 'Premium',
    price: '$20',
    cadence: 'per month',
    summary: 'The same tools as Standard, with the headroom for heavy research days.',
    features: [
      { text: '50 research queries a day (resets 00:00 UTC)' },
      { text: 'Everything in Standard' },
      { text: 'Every relevant judgment, ten at a time' },
      { text: 'All tools: analyse, compare, download, copy' },
      { text: 'Cancel anytime — access kept until period end' },
    ],
    cta: 'Get Premium',
    emphasis: false,
    checkout: true,
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
  const isLoggedIn = useIsLoggedIn();
  const plan = usePlan();
  // The signed-in user's plan, once the server has confirmed it.
  const current = isLoggedIn && plan.confirmed ? plan.key : null;
  const [busy, setBusy] = useState(null); // the plan whose checkout is opening
  const [payError, setPayError] = useState('');
  useToastOn(payError, 'error');

  // Every paid plan, including a switch between Standard and Premium, is
  // bought on Stripe's hosted Checkout page: it shows the price and takes the
  // payment, so no extra confirmation is needed here. After paying for the
  // new plan, the server cancels the old subscription.
  const onSubscribe = async (target) => {
    if (busy) return;
    setPayError('');
    setBusy(target);
    const result = await startCheckout(target);
    if (!result.ok) {
      setBusy(null);
      if (result.reason === 'signin') {
        toast.error('Please sign in to subscribe.');
        navigate('/login', { state: { next: '/pricing' } });
        return;
      }
      setPayError(result.message);
    }
    // On success the browser is already on its way to Stripe.
  };

  const ctaLabel = (key, cta) => {
    if (busy === key) return 'Opening secure checkout…';
    if (current === key) return 'Your current plan';
    if (current && current !== 'free') return `Switch to ${key === 'premium' ? 'Premium' : 'Standard'}`;
    return cta;
  };

  return (
    <section aria-labelledby="plans-title" className="w-full px-5 py-12 sm:px-8 md:py-16 overflow-x-hidden">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Pricing"
          icon="sell"
          title={<span id="plans-title">Start free.</span>}
          accent="Upgrade when the research gets serious."
          lede="Free finds the judgments that match your case. Standard and Premium add every research tool — they differ only in how many searches you get each day."
          className="mx-auto"
        />

        {/* Pricing Cards */}
        <div className="pricing-deck relative mx-auto mt-10 max-w-[1140px] md:mt-12 lg:py-10">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 lg:gap-3 items-stretch">
            {PLANS.map(({ key, name, price, cadence, summary, features, cta, to, emphasis, checkout }, index) => {
              const cardPositionClass =
                index === 0
                  ? 'pricing-card-left'
                  : index === 1
                  ? 'pricing-card-center'
                  : 'pricing-card-right';

              return (
                <div
                  key={name}
                  className={`pricing-card border-trace ${cardPositionClass} relative flex flex-col justify-between overflow-hidden rounded-4xl p-8 sm:p-9 ${
                    emphasis
                      ? 'bg-gradient-to-br from-[#0066f6] via-[#004ecc] to-[#1f00db] text-white shadow-glow-lg'
                      : 'border border-ash-200 bg-white shadow-soft hover:border-brand-200'
                  }`}
                >
                  {/* Floating randomly moving bubbles */}
                  <CardBubbles tone={emphasis ? 'light' : 'dark'} density="compact" />

                  <div className="relative z-[2]">
                    {(emphasis || current === key) && (
                      <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-white px-4 py-1 font-ui text-[11px] font-bold uppercase tracking-[0.1em] text-brand-800 shadow-card ring-1 ring-ash-200">
                        {current === key ? 'Your plan' : 'Most popular'}
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
                      {features.map(({ text, locked }) => (
                        <li key={text} className="flex items-start gap-3">
                          <span
                            aria-hidden="true"
                            className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                              locked
                                ? 'bg-ash-100 text-ash-400'
                                : emphasis
                                  ? 'bg-white/20 text-white'
                                  : 'bg-mint-400/20 text-mint-700'
                            }`}
                          >
                            <span className="material-symbols-outlined text-[13px]">{locked ? 'lock' : 'check'}</span>
                          </span>
                          <span
                            className={`font-prose text-[14px] leading-[1.6] ${
                              locked ? 'text-ash-400' : emphasis ? 'text-white/90' : 'text-ash-700'
                            }`}
                          >
                            {locked && <span className="sr-only">Not included: </span>}
                            {text}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {checkout ? (
                    <button
                      type="button"
                      onClick={() => onSubscribe(key)}
                      disabled={Boolean(busy) || current === key}
                      className={`relative z-[2] mt-9 inline-flex items-center justify-center rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-70 ${
                        emphasis
                          ? 'bg-white text-brand-800 hover:-translate-y-0.5 hover:shadow-card-lg'
                          : 'border border-ash-300 text-ash-800 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                      }`}
                    >
                      {ctaLabel(key, cta)}
                    </button>
                  ) : (
                    <Link
                      to={name === 'Free' && isLoggedIn ? '/welcome' : to}
                      className={`relative z-[2] mt-9 inline-flex items-center justify-center rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold transition-all duration-300 ${
                        emphasis
                          ? 'bg-white text-brand-800 hover:-translate-y-0.5 hover:shadow-card-lg'
                          : 'border border-ash-300 text-ash-800 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                      }`}
                    >
                      {name === 'Free' && isLoggedIn ? 'Research Workplace' : cta}
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
          Billed monthly in US dollars, exclusive of applicable tax. Switch between Standard and
          Premium, or cancel, at any time.
        </Reveal>
      </div>
    </section>
  );
};

export default PlansSection;
