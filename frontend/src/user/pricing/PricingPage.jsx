import { useState } from 'react';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import DivisionsTicker from '../components/bound/DivisionsTicker';
import PlansSection from '../components/bound/PlansSection';
import AuthorityStrip from '../components/bound/AuthorityStrip';
import ClosingCTA from '../components/bound/ClosingCTA';
import Reveal from '../components/Reveal';
import SectionOpener from '../components/bound/SectionOpener';

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
            { icon: 'balance', label: 'Rs 2,400 / mo advocate' },
            { icon: 'groups', label: 'Pooled seats for chambers' },
          ]}
        />
        <DivisionsTicker />

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
