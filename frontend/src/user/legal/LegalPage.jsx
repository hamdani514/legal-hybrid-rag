import React from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';
import UserHeader from '../components/UserHeader';
import UserFooter from '../components/UserFooter';
import PageBanner from '../components/PageBanner';
import ActionLink from '../components/ui/ActionLink';
import { GoldRule } from '../components/cinematic/Atmosphere';
import { VIEWPORT_SOFT, fadeUp, stagger } from '../motion';
import { LEGAL_DOCUMENTS } from './legalDocuments';

const SIBLINGS = [
  { slug: 'privacy', label: 'Privacy Policy' },
  { slug: 'terms', label: 'Terms of Service' },
  { slug: 'disclaimer', label: 'Legal Disclaimer' },
];

/**
 * One template for the three policy pages linked from the footer, keyed by
 * the :slug route param. Long-form copy gets a sticky contents rail on
 * large screens and a plain stacked read on small ones.
 */
const LegalPage = () => {
  // Each policy has its own top-level path (/privacy, /terms, /disclaimer),
  // so the slug comes from the pathname rather than a route param.
  const { pathname } = useLocation();
  const slug = pathname.replace(/^\/+/, '');
  const doc = LEGAL_DOCUMENTS[slug];

  // An unknown policy slug is a bad URL, not a blank page.
  if (!doc) return <Navigate to="/faq" replace />;

  return (
    <div className="flex min-h-screen w-full flex-col bg-parchment-50">
      <UserHeader />

      <main id="main-content" className="w-full flex-1">
        <PageBanner
          size="sm"
          art="none"
          eyebrow={doc.eyebrow}
          title={doc.banner}
          subtitle={doc.summary}
          breadcrumb={[{ label: 'Home', to: '/' }, { label: doc.title }]}
        />

        <div className="mx-auto grid w-full max-w-[1120px] grid-cols-1 gap-12 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-12 lg:gap-16 lg:py-24">
          {/* Contents rail */}
          <nav aria-label="On this page" className="lg:col-span-4 lg:sticky lg:top-28 lg:self-start">
            <h2 className="font-body text-[11px] font-bold uppercase tracking-[0.22em] text-gold-600">
              On this page
            </h2>
            <GoldRule width="w-14" className="mt-3" />
            <ol className="mt-5 flex flex-col gap-2.5">
              {doc.sections.map((section, index) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="link-wipe inline-flex gap-3 font-body text-sm text-ink-500 transition-colors hover:text-ink-800"
                  >
                    <span className="font-headline italic text-gold-700">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    {section.heading}
                  </a>
                </li>
              ))}
            </ol>

            <div className="mt-9 rounded-lg border border-ink-800/10 bg-white p-5">
              <p className="font-body text-[11px] uppercase tracking-[0.18em] text-ink-400">
                Related policies
              </p>
              <ul className="mt-3 flex flex-col gap-2">
                {SIBLINGS.filter((s) => s.slug !== doc.slug).map((sibling) => (
                  <li key={sibling.slug}>
                    <Link
                      to={`/${sibling.slug}`}
                      className="link-wipe font-body text-sm text-ink-700 transition-colors hover:text-gold-600"
                    >
                      {sibling.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          {/* Body */}
          <motion.article
            className="lg:col-span-8"
            variants={stagger(0.08)}
            initial="hidden"
            whileInView="show"
            viewport={VIEWPORT_SOFT}
          >
            <motion.p variants={fadeUp} className="font-body text-xs uppercase tracking-[0.18em] text-ink-400">
              {doc.updated}
            </motion.p>

            {doc.sections.map((section, index) => (
              <motion.section
                key={section.id}
                id={section.id}
                variants={fadeUp}
                aria-labelledby={`${section.id}-heading`}
                className="scroll-mt-28 border-t border-ink-800/10 py-9 first-of-type:border-t-0 first-of-type:pt-7"
              >
                <div className="flex items-baseline gap-4">
                  <span aria-hidden="true" className="font-headline text-xl italic text-gold-700">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <h2
                    id={`${section.id}-heading`}
                    className="font-headline text-2xl font-semibold tracking-[-0.02em] text-ink-800"
                  >
                    {section.heading}
                  </h2>
                </div>

                <div className="mt-5 flex flex-col gap-4 pl-0 sm:pl-10">
                  {section.body.map((paragraph) => (
                    <p key={paragraph} className="max-w-[70ch] font-body text-base leading-8 text-ink-600">
                      {paragraph}
                    </p>
                  ))}
                </div>
              </motion.section>
            ))}

            <motion.div
              variants={fadeUp}
              className="mt-10 flex flex-wrap gap-4 border-t border-ink-800/10 pt-9"
            >
              <ActionLink to="/contact" variant="ink" size="md" icon="mail">
                Ask about this policy
              </ActionLink>
              <ActionLink to="/faq" variant="outline" size="md" icon="help">
                Read the FAQ
              </ActionLink>
            </motion.div>
          </motion.article>
        </div>
      </main>

      <UserFooter />
    </div>
  );
};

export default LegalPage;
