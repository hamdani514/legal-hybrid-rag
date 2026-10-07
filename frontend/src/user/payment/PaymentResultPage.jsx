import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import Reveal from '../components/Reveal';
import { confirmCheckout, paymentStatus } from '../lib/payments';

/**
 * Where Stripe sends the browser back to: /payment/success and
 * /payment/cancel, one template for both.
 *
 * The success page does NOT assume the payment worked. Stripe's webhook is
 * what upgrades the plan, and it can land a second or two after the redirect,
 * so this asks the server what the plan actually is and keeps asking for a
 * short while. Anything else would tell a reader their plan had changed on
 * the strength of a URL they could have typed themselves.
 */
const POLL_ATTEMPTS = 8;
const POLL_EVERY_MS = 1500;

const PaymentResultPage = () => {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const cancelled = pathname.includes('cancel');

  const [state, setState] = useState(cancelled ? 'cancelled' : 'confirming');
  const [plan, setPlan] = useState('');

  // Shows the confirmed plan and keeps the stored account label in step.
  const applyPlan = (name) => {
    setPlan(name);
    setState('confirmed');
    try {
      const stored = JSON.parse(localStorage.getItem('currentUser') || 'null');
      if (stored) localStorage.setItem('currentUser', JSON.stringify({ ...stored, plan: name }));
    } catch {
      /* a stale label is not worth failing over */
    }
  };

  useEffect(() => {
    if (cancelled) return undefined;
    let live = true;
    let attempts = 0;

    const ask = async () => {
      // First time round, settle it directly with Stripe rather than waiting
      // for a webhook that may never arrive (localhost, or an endpoint not
      // yet configured on the host).
      if (attempts === 0) {
        const settled = await confirmCheckout(params.get('session_id'));
        if (!live) return;
        if (settled?.is_paid) {
          applyPlan(settled.plan);
          return;
        }
      }
      const status = await paymentStatus();
      if (!live) return;
      if (status?.is_paid) {
        applyPlan(status.plan);
        return;
      }
      attempts += 1;
      if (attempts >= POLL_ATTEMPTS) {
        setState('pending');
        return;
      }
      setTimeout(ask, POLL_EVERY_MS);
    };

    ask();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cancelled]);

  const VIEW = {
    confirming: {
      icon: 'hourglass_top',
      tone: 'text-brand-600 bg-brand-50',
      title: 'Confirming your payment',
      accent: 'with Stripe',
      body: 'This takes a moment. We are waiting for Stripe to confirm the charge before changing anything on your account.',
    },
    confirmed: {
      icon: 'verified',
      tone: 'text-green-700 bg-mint-400/20',
      title: 'You are on the',
      accent: `${plan || 'Standard'} plan`,
      body: 'Stripe has confirmed the payment and your account has been upgraded. You can start researching straight away.',
    },
    pending: {
      icon: 'schedule',
      tone: 'text-amber-700 bg-amber-400/15',
      title: 'Payment received,',
      accent: 'still being confirmed',
      body: 'Stripe has taken the payment but has not finished confirming it with us. This usually settles within a minute — reload this page shortly, and nothing is lost if you close it.',
    },
    cancelled: {
      icon: 'remove_shopping_cart',
      tone: 'text-ash-600 bg-ash-100',
      title: 'Checkout was',
      accent: 'cancelled',
      body: 'No payment was taken and your plan has not changed. You can pick up where you left off whenever you are ready.',
    },
  }[state];

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main id="main-content" className="ground-light w-full flex-1 px-5 py-24 sm:px-8 md:py-32">
        <div className="mx-auto flex max-w-[44rem] flex-col items-center text-center">
          <Reveal variant="scale">
            <span
              aria-hidden="true"
              className={`flex h-20 w-20 items-center justify-center rounded-3xl ${VIEW.tone}`}
            >
              <span
                className={`material-symbols-outlined text-[36px] ${
                  state === 'confirming' ? 'animate-spin' : ''
                }`}
              >
                {VIEW.icon}
              </span>
            </span>
          </Reveal>

          <Reveal
            as="h1"
            variant="mask"
            delay={120}
            className="mt-8 font-display text-[clamp(2rem,4.6vw,3rem)] font-bold leading-[1.1] tracking-[-0.03em] text-balance text-ash-900"
          >
            {VIEW.title} <span className="grad-text">{VIEW.accent}</span>
          </Reveal>

          <Reveal
            as="p"
            delay={240}
            className="mt-5 max-w-[34rem] font-prose text-[1.0625rem] leading-[1.75] text-ash-600"
          >
            {VIEW.body}
          </Reveal>

          <Reveal delay={340} className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/welcome"
              className="grad-btn inline-flex items-center gap-2 rounded-full px-6 py-3.5 font-ui text-[14.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg"
            >
              <span className="material-symbols-outlined text-[18px]">gavel</span>
              Go to your research
            </Link>
            <Link
              to="/pricing"
              className="inline-flex items-center rounded-full border border-ash-300 px-6 py-3.5 font-ui text-[14.5px] font-bold text-ash-800 transition-all duration-300 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
            >
              {cancelled ? 'Back to pricing' : 'View plans'}
            </Link>
          </Reveal>

          {params.get('session_id') && (
            <Reveal as="p" variant="fade" delay={420} className="mt-8 font-prose text-[12px] text-ash-400">
              Stripe reference {params.get('session_id').slice(0, 24)}…
            </Reveal>
          )}
        </div>
      </main>

      <SiteFoot />
    </div>
  );
};

export default PaymentResultPage;
