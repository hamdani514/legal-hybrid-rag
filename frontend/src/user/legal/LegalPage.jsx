import { useEffect, useState } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import { LEGAL_DOCUMENTS } from './legalDocuments';

const SIBLINGS = [
  { slug: 'privacy', label: 'Privacy Policy', icon: 'lock' },
  { slug: 'terms', label: 'Terms of Service', icon: 'gavel' },
  { slug: 'disclaimer', label: 'Legal Disclaimer', icon: 'warning' },
];

/**
 * Tracks which section is currently in view so the contents rail can mark it.
 * Falls back to the first id when IntersectionObserver is unavailable, so the
 * rail is never left with nothing highlighted.
 */
const useActiveSection = (ids) => {
  const [active, setActive] = useState(() => ids[0] ?? '');

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        // The topmost heading currently on screen wins, so scrolling up
        // moves the marker back rather than sticking at the deepest section.
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      // Bias the band to the upper third so a heading registers as it arrives.
      { rootMargin: '-96px 0px -62% 0px', threshold: 0 }
    );

    ids.forEach((id) => {
      const node = document.getElementById(id);
      if (node) observer.observe(node);
    });

    return () => observer.disconnect();
  }, [ids]);

  return active;
};

/**
 * One template for the three policy documents, keyed by the pathname slug.
 * Long-form legal copy gets a sticky contents rail on large screens and a
 * plain stacked read on small ones.
 */
const LegalPage = () => {
  // Each policy has its own top-level path (/privacy, /terms, /disclaimer),
  // so the slug comes from the pathname rather than a route param.
  const { pathname } = useLocation();
  const slug = pathname.replace(/^\/+/, '');
  const doc = LEGAL_DOCUMENTS[slug];

  const ids = doc ? doc.sections.map((section) => section.id) : [];
  const active = useActiveSection(ids);

  // An unknown policy slug is a bad URL, not a blank page.
  if (!doc) return <Navigate to="/faq" replace />;

  // `banner` carries a pipe where the headline should break.
  const [lead, accent] = doc.banner.split('|');

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main id="main-content" className="w-full flex-1">
        {/* ── Masthead ─────────────────────────────────────────────── */}
        <header className="ground-light relative w-full overflow-hidden">
          <span
            aria-hidden="true"
            className="float-y-slow pointer-events-none absolute -right-24 top-12 h-72 w-72 rounded-full bg-brand-200/30 blur-3xl"
          />

          <div className="relative mx-auto w-full max-w-[1200px] px-5 pb-14 pt-32 sm:px-8 sm:pb-16 sm:pt-36">
            <nav aria-label="Breadcrumb" className="pop-in">
              <ol className="flex items-center gap-2 font-prose text-[13px] text-ash-500">
                <li>
                  <Link to="/" className="transition-colors hover:text-brand-700">
                    Home
                  </Link>
                </li>
                <li aria-hidden="true">/</li>
                <li className="font-semibold text-ash-700">{doc.title}</li>
              </ol>
            </nav>

            <span
              className="pop-in mt-7 inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700"
              style={{ '--i': 1 }}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                description
              </span>
              {doc.eyebrow}
            </span>

            <h1
              className="pop-in mt-6 max-w-[44rem] font-display text-[clamp(2.25rem,6vw,3.75rem)] font-bold leading-[1.05] tracking-[-0.035em] text-balance text-ash-900"
              style={{ '--i': 2 }}
            >
              {lead} {accent && <span className="grad-text">{accent}</span>}
            </h1>

            <p
              className="pop-in mt-6 max-w-[44rem] font-prose text-[1.0625rem] leading-[1.78] text-ash-600"
              style={{ '--i': 3 }}
            >
              {doc.summary}
            </p>

            <p
              className="pop-in mt-8 inline-flex items-center gap-2 rounded-full border border-ash-200 bg-white px-4 py-2 font-prose text-[12.5px] text-ash-500 shadow-soft"
              style={{ '--i': 4 }}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                event_available
              </span>
              {doc.updated}
            </p>
          </div>
        </header>

        {/* ── Body ─────────────────────────────────────────────────── */}
        <div className="mx-auto grid w-full max-w-[1200px] grid-cols-1 gap-10 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-[16rem_1fr] lg:gap-14">
          {/* Contents rail */}
          <aside className="self-start lg:sticky lg:top-28">
            <h2 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-ash-900">
              On this page
            </h2>

            <nav aria-label="Sections" className="mt-4">
              <ol className="flex flex-col gap-0.5 border-l border-ash-200">
                {doc.sections.map((section) => {
                  const isActive = active === section.id;
                  return (
                    <li key={section.id}>
                      <a
                        href={`#${section.id}`}
                        aria-current={isActive ? 'true' : undefined}
                        className={`-ml-px block border-l-2 py-2 pl-4 font-prose text-[13.5px] leading-5 transition-colors duration-250 ${
                          isActive
                            ? 'border-brand-500 font-semibold text-brand-700'
                            : 'border-transparent text-ash-500 hover:border-ash-300 hover:text-ash-800'
                        }`}
                      >
                        {section.heading}
                      </a>
                    </li>
                  );
                })}
              </ol>
            </nav>

            {/* The other two policies */}
            <div className="mt-9 border-t border-ash-200 pt-7">
              <h2 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-ash-900">
                Related
              </h2>
              <ul className="mt-4 flex flex-col gap-2">
                {SIBLINGS.filter((sibling) => sibling.slug !== slug).map(
                  ({ slug: siblingSlug, label, icon }) => (
                    <li key={siblingSlug}>
                      <Link
                        to={`/${siblingSlug}`}
                        className="group flex items-center gap-3 rounded-2xl border border-ash-200 bg-white px-4 py-3 transition-all duration-300 hover:border-brand-200 hover:shadow-soft"
                      >
                        <span
                          aria-hidden="true"
                          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
                        >
                          <span className="material-symbols-outlined text-[16px]">{icon}</span>
                        </span>
                        <span className="font-display text-[13px] font-semibold text-ash-800">
                          {label}
                        </span>
                      </Link>
                    </li>
                  )
                )}
              </ul>
            </div>
          </aside>

          {/* The document */}
          <article className="min-w-0">
            {doc.sections.map((section, index) => (
              <section
                key={section.id}
                id={section.id}
                // Clear the sticky header when jumped to from the rail.
                className="scroll-mt-28 border-ash-200 pt-10 first:pt-0 [&:not(:first-child)]:border-t"
              >
                <div className="flex items-baseline gap-3">
                  <span
                    aria-hidden="true"
                    className="font-display text-[13px] font-bold tabular-nums text-brand-500"
                  >
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <h2 className="font-display text-[clamp(1.375rem,2.6vw,1.75rem)] font-bold leading-snug tracking-[-0.02em] text-ash-900">
                    {section.heading}
                  </h2>
                </div>

                <div className="mt-5 flex flex-col gap-4 pb-10">
                  {section.body.map((paragraph, i) => (
                    <p
                      key={i}
                      className="max-w-[68ch] font-prose text-[15.5px] leading-[1.8] text-ash-600"
                    >
                      {paragraph}
                    </p>
                  ))}
                </div>
              </section>
            ))}

            {/* Questions about the document itself */}
            <div className="mt-4 rounded-3xl border border-ash-200 bg-ash-50 p-7 sm:p-8">
              <h2 className="font-display text-[17px] font-bold tracking-[-0.015em] text-ash-900">
                Questions about this {doc.eyebrow.toLowerCase()}?
              </h2>
              <p className="mt-3 max-w-[52ch] font-prose text-[14.5px] leading-[1.7] text-ash-600">
                Write to us and a person will answer. For anything touching your own matter,
                instruct an advocate — nothing here is legal advice.
              </p>
              <Link
                to="/contact"
                className="grad-btn group mt-6 inline-flex items-center gap-2 rounded-full px-6 py-3 font-ui text-[14px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
              >
                Contact us
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[17px] transition-transform duration-300 group-hover:translate-x-1"
                >
                  arrow_forward
                </span>
              </Link>
            </div>
          </article>
        </div>
      </main>

      <SiteFoot />
    </div>
  );
};

export default LegalPage;
