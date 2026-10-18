import { useState, useEffect } from 'react';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import DivisionsTicker from '../components/bound/DivisionsTicker';
import PlansSection from '../components/bound/PlansSection';
import AuthorityStrip from '../components/bound/AuthorityStrip';
import ClosingCTA from '../components/bound/ClosingCTA';
import Reveal from '../components/Reveal';
import SectionOpener from '../components/bound/SectionOpener';
import { paymentStatus, cancelSubscription, reactivateSubscription } from '../lib/payments';

/**
 * Frequently Asked Billing & Enrolment Questions.
 */
const PRICING_FAQS = [
  {
    q: 'How does student verification work?',
    a: 'Register with your official law faculty or university email (.edu.pk or recognized institution). Complimentary research access is automatically activated for your academic session.',
  },
  {
    q: 'What payment methods do you support in Pakistan?',
    a: 'We accept all major Pakistani payment methods including Visa, Mastercard, PayPak, Raast direct transfer, and mobile wallets (JazzCash and Nayapay).',
  },
  {
    q: 'Can I upgrade, downgrade or cancel anytime?',
    a: 'Yes, with a single click in your account settings. Subscriptions can be managed or canceled anytime with zero hidden fees or lock-ins.',
  },
  {
    q: 'Do you offer custom chamber packages for law firms?',
    a: 'Yes. For chambers and legal teams with multiple associates, we offer pooled research sessions, shared case history, and direct invoice billing.',
  },
  {
    q: 'Is my research query data private and confidential?',
    a: 'Strictly yes. We honor advocate-client privilege standards: your queries and research trails are encrypted and never used to train or refine public AI models.',
  },
];

const PricingPage = () => {
  const [openFaq, setOpenFaq] = useState(null);
  const [status, setStatus] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [reactivating, setReactivating] = useState(false);

  useEffect(() => {
    paymentStatus().then((s) => {
      if (s) setStatus(s);
    });
  }, []);

  const handleCancel = async () => {
    const ends = status?.subscriptionEndsAt
      ? new Date(status.subscriptionEndsAt).toLocaleDateString()
      : 'period end';
    if (
      !window.confirm(
        `Are you sure? You'll keep access until ${ends}, then downgrade to Free (1 query/day). Your payment card will be removed automatically.`
      )
    )
      return;

    setCancelling(true);
    const res = await cancelSubscription();
    alert(res?.message || 'Subscription cancelled.');
    setCancelling(false);
    const updated = await paymentStatus();
    if (updated) setStatus(updated);
  };

  const handleReactivate = async () => {
    setReactivating(true);
    const res = await reactivateSubscription();
    alert(res?.message || 'Subscription reactivated.');
    setReactivating(false);
    const updated = await paymentStatus();
    if (updated) setStatus(updated);
  };

  const toggleFaq = (idx) => {
    setOpenFaq((curr) => (curr === idx ? null : idx));
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main id="main-content" className="w-full flex-1">
        <HomeHero
          badge="Transparent Subscription Plans · Zero Hidden Tiers"
          title="Predictable pricing for students and"
          accent="chambers of every size"
          description="Full unrestricted access to indexed Supreme Court precedents. Completely free for law students, simple monthly plans for advocates, and pooled seats for chambers."
          primaryCta={{ to: '/signup', label: 'Get started free', icon: 'arrow_forward' }}
          secondaryCta={{ to: '/contact', label: 'Chamber bulk onboarding', icon: 'corporate_fare' }}
          highlights={[
            { icon: 'school', label: 'Free for verified students' },
            { icon: 'balance', label: '$10 / mo standard' },
            { icon: 'groups', label: 'Pooled seats for chambers' },
          ]}
        />
        <DivisionsTicker />

        {/* User Active Subscription State Banner */}
        {status && (
          <div className="mx-auto max-w-4xl px-5 pt-10">
            {status.plan === 'standard' && !status.cancelAtPeriodEnd && (
              <div className="rounded-3xl border border-emerald-200 bg-emerald-50/80 p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center justify-between gap-5 shadow-sm">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                    <h3 className="font-display font-bold text-base text-emerald-950">Current Plan: Standard</h3>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-100 px-2.5 py-0.5 rounded-full border border-emerald-300">
                      Active
                    </span>
                  </div>
                  <p className="text-xs font-prose text-emerald-800 mt-2">
                    ✅ <strong>20 queries/day</strong> · Used today: <strong>{status.dailyQueriesUsed}/{status.dailyQueriesLimit}</strong> · Renews on {status.subscriptionEndsAt ? new Date(status.subscriptionEndsAt).toLocaleDateString() : 'next cycle'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="shrink-0 px-4 py-2.5 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-1.5"
                >
                  <span className="material-symbols-outlined text-[16px]">cancel</span>
                  <span>{cancelling ? 'Cancelling...' : 'Cancel Subscription'}</span>
                </button>
              </div>
            )}

            {status.plan === 'standard' && status.cancelAtPeriodEnd && (
              <div className="rounded-3xl border-2 border-amber-300 bg-amber-50 p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center justify-between gap-5 shadow-sm">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-amber-700 text-[22px]">warning</span>
                    <h3 className="font-display font-bold text-base text-amber-950">Subscription Ending</h3>
                  </div>
                  <p className="text-xs font-prose text-amber-900 mt-2 leading-relaxed">
                    Your access remains active until <strong>{status.subscriptionEndsAt ? new Date(status.subscriptionEndsAt).toLocaleDateString() : 'period end'}</strong>. On that date, you'll downgrade to Free (1 query/day) and your payment card will be removed automatically.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleReactivate}
                  disabled={reactivating}
                  className="shrink-0 px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5"
                >
                  <span className="material-symbols-outlined text-[16px]">restart_alt</span>
                  <span>{reactivating ? 'Reactivating...' : 'Reactivate Subscription'}</span>
                </button>
              </div>
            )}

            {status.plan === 'free' && (
              <div className="rounded-3xl border border-ash-200 bg-ash-50/70 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="font-display font-bold text-base text-ash-900">Current Plan: Free Tier</h3>
                  <p className="text-xs font-prose text-ash-600 mt-1">
                    1 query/day · Used today: <strong>{status.dailyQueriesUsed}/{status.dailyQueriesLimit}</strong> · Quota resets every 24h at 00:00 UTC
                  </p>
                </div>
                <span className="text-xs font-semibold text-brand-700 bg-brand-50 border border-brand-200 px-3.5 py-1.5 rounded-xl">
                  Standard plan available below
                </span>
              </div>
            )}
          </div>
        )}

        {/* Pricing Cards Section with Interactive Card Fan Animation */}
        <PlansSection />

        {/* Credibility & Guarantee Strip */}
        <AuthorityStrip />

        {/* Frequently Asked Questions */}
        <section aria-labelledby="pricing-faq-title" className="w-full px-5 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[840px]">
            <SectionOpener
              eyebrow="Billing Questions"
              icon="help"
              title={<span id="pricing-faq-title">Frequently asked billing &</span>}
              accent="subscription questions"
              lede="Have questions about student enrolment, payment methods, or invoicing? Find answers below."
              className="mx-auto"
            />

            <div className="mt-12 flex flex-col gap-3.5 sm:mt-16">
              {PRICING_FAQS.map((faq, idx) => {
                const isOpen = openFaq === idx;
                return (
                  <Reveal
                    key={faq.q}
                    delay={idx * 60}
                    className="overflow-hidden rounded-3xl border border-ash-200 bg-white transition-all hover:border-brand-200 hover:shadow-soft"
                  >
                    <button
                      type="button"
                      onClick={() => toggleFaq(idx)}
                      className="flex w-full items-center justify-between gap-4 p-5 text-left sm:p-6"
                      aria-expanded={isOpen}
                    >
                      <span className="font-display text-[15.5px] font-semibold text-ash-900 sm:text-[16.5px]">
                        {faq.q}
                      </span>
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ash-100 text-ash-600 transition-transform duration-300 ${
                          isOpen ? 'rotate-180 bg-brand-50 text-brand-600' : ''
                        }`}
                      >
                        <span className="material-symbols-outlined text-[18px]">expand_more</span>
                      </span>
                    </button>
                    {isOpen && (
                      <div className="border-t border-ash-100 px-5 pb-6 pt-4 font-prose text-[14.5px] leading-[1.75] text-ash-600 sm:px-6">
                        {faq.a}
                      </div>
                    )}
                  </Reveal>
                );
              })}
            </div>
          </div>
        </section>

        {/* Closing Call to Action */}
        <ClosingCTA
          eyebrow="Get started today"
          title="Start your first legal query in"
          accent="under 60 seconds."
          lede="Join advocates and researchers finding the binding reasoning behind Supreme Court precedents."
          primary={{ to: '/signup', label: 'Start researching free' }}
          secondary={{ to: '/contact', label: 'Speak with our team' }}
        />
      </main>

      <SiteFoot />
    </div>
  );
};

export default PricingPage;
