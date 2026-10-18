import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import Reveal from '../components/Reveal';
import BlogCard from './BlogCard';
import { prepareArticle } from './articleHtml';
import { apiFetch } from '../../lib/api';

// The sticky header is 76px; headings must clear it when the rail jumps to one.
const SCROLL_OFFSET = 108;

/**
 * Marks the section currently being read, so the contents rail tracks the page.
 * Mirrors the rail on the policy pages (user/legal/LegalPage.jsx).
 */
const useActiveSection = (ids) => {
  const [observed, setObserved] = useState('');

  useEffect(() => {
    if (!ids.length) return undefined;
    if (typeof IntersectionObserver === 'undefined') return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        // The topmost heading on screen wins, so scrolling up moves the marker
        // back rather than sticking at the deepest section.
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setObserved(visible[0].target.id);
      },
      { rootMargin: '-112px 0px -62% 0px', threshold: 0 }
    );

    ids.forEach((id) => {
      const node = document.getElementById(id);
      if (node) observer.observe(node);
    });

    return () => observer.disconnect();
  }, [ids]);

  // Before anything has been observed — and on an article whose ids have just
  // changed — the first section is the one being read.
  return ids.includes(observed) ? observed : ids[0] || '';
};

/**
 * One article: the body the editor stored as HTML, a contents rail built from
 * its own h2s, and the related reading the API sends alongside it.
 *
 * The body is sanitized in articleHtml.js before it is injected — see the note
 * there on why the allowlist is narrow.
 */
const BlogDetailPage = () => {
  const { slug } = useParams();
  const [blog, setBlog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });

    const load = async () => {
      setLoading(true);
      setError('');
      setBlog(null);
      try {
        const response = await apiFetch(`/api/blogs/${encodeURIComponent(slug)}`);
        if (response.status === 404) throw new Error('missing');
        if (!response.ok) throw new Error('failed');
        const data = await response.json();
        if (!cancelled) setBlog(data);
      } catch (caught) {
        if (cancelled) return;
        setError(
          caught.message === 'missing'
            ? 'That article does not exist, or it has been unpublished.'
            : 'We could not load this article just now.'
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // The tab title is how a reader keeps several articles open side by side.
  useEffect(() => {
    if (!blog) return undefined;
    const previous = document.title;
    document.title = `${blog.title} · Verdict AI`;
    return () => {
      document.title = previous;
    };
  }, [blog]);

  const { html, toc } = useMemo(
    () => prepareArticle(blog?.contentHtml),
    [blog?.contentHtml]
  );

  const ids = useMemo(() => toc.map((entry) => entry.id), [toc]);
  const active = useActiveSection(ids);

  const jumpTo = (event, id) => {
    event.preventDefault();
    const node = document.getElementById(id);
    if (!node) return;
    const top = node.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
    window.scrollTo({ top, behavior: 'smooth' });
    // The hash makes the position shareable; replaceState keeps every jump out
    // of the back button's history.
    window.history.replaceState(null, '', `#${id}`);
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main id="main-content" className="w-full flex-1">
        {loading ? (
          <div
            role="status"
            aria-live="polite"
            className="mx-auto w-full max-w-3xl animate-pulse px-5 pb-24 pt-32 sm:px-8 sm:pt-36"
          >
            <span className="sr-only">Loading article</span>
            <div className="mx-auto h-4 w-32 rounded bg-ash-100" />
            <div className="mx-auto mt-7 h-10 w-full rounded bg-ash-100" />
            <div className="mx-auto mt-3 h-10 w-2/3 rounded bg-ash-100" />
            <div className="mt-10 h-[320px] w-full rounded-3xl bg-ash-100" />
          </div>
        ) : error ? (
          <div className="mx-auto flex w-full max-w-xl flex-col items-center px-5 pb-28 pt-40 text-center sm:px-8">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[40px] text-ash-400"
            >
              find_in_page
            </span>
            <h1 className="mt-5 font-display text-[clamp(1.5rem,4vw,2rem)] font-bold tracking-[-0.025em] text-ash-900">
              Article unavailable
            </h1>
            <p className="mt-3 font-prose text-[15.5px] leading-[1.75] text-ash-600">{error}</p>
            <Link
              to="/blogs"
              className="grad-btn mt-8 inline-flex items-center gap-2 rounded-full px-7 py-3.5 font-ui text-[14.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                arrow_back
              </span>
              Return to all insights
            </Link>
          </div>
        ) : (
          blog && (
            <>
              {/* ── Article masthead ─────────────────────────────── */}
              <div className="mx-auto w-full max-w-4xl px-5 pt-32 sm:px-8 sm:pt-36">
                <Link
                  to="/blogs"
                  className="group inline-flex items-center gap-2 font-ui text-[13.5px] font-semibold text-ash-500 transition-colors hover:text-brand-700"
                >
                  <span
                    aria-hidden="true"
                    className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover:-translate-x-1"
                  >
                    arrow_back
                  </span>
                  All Articles
                </Link>

                <header className="mx-auto mt-8 max-w-3xl text-center">
                  <span className="inline-flex items-center rounded-full bg-brand-50 px-3.5 py-1.5 font-ui text-[12px] font-semibold uppercase tracking-[0.08em] text-brand-700">
                    {blog.category}
                  </span>

                  <h1 className="mt-6 font-display text-[clamp(2rem,5vw,3.125rem)] font-bold leading-[1.1] tracking-[-0.035em] text-balance text-ash-900">
                    {blog.title}
                  </h1>

                  <p className="mt-5 font-prose text-[1.0625rem] leading-[1.8] text-ash-600">
                    {blog.excerpt}
                  </p>

                  <div className="mt-8 flex flex-wrap items-center justify-center gap-x-3 gap-y-3 font-ui text-[13px] text-ash-500">
                    <span className="inline-flex items-center gap-2.5">
                      <img
                        src={blog.author.avatar || '/assets/user.png'}
                        alt=""
                        loading="lazy"
                        className="h-8 w-8 rounded-full border border-ash-200 object-cover"
                      />
                      <span>
                        By <strong className="font-semibold text-ash-900">{blog.author.name}</strong>
                      </span>
                    </span>
                    <span aria-hidden="true" className="text-ash-300">·</span>
                    <span className="inline-flex items-center gap-1.5 font-semibold text-brand-700">
                      <span aria-hidden="true" className="material-symbols-outlined text-[17px]">
                        schedule
                      </span>
                      {blog.readTime}
                    </span>
                    <span aria-hidden="true" className="text-ash-300">·</span>
                    <span>{blog.publishedAt}</span>
                  </div>
                </header>

                {blog.coverImage && (
                  <Reveal variant="scale" className="mt-11">
                    <div className="overflow-hidden rounded-3xl border border-ash-200 bg-ash-100 shadow-card">
                      <img
                        src={blog.coverImage}
                        alt=""
                        className="max-h-[460px] w-full object-cover"
                      />
                    </div>
                  </Reveal>
                )}
              </div>

              {/* ── Rail + body ──────────────────────────────────── */}
              <div className="mx-auto w-full max-w-[1200px] px-5 pb-20 pt-14 sm:px-8">
                <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
                  <aside className="lg:col-span-4 xl:col-span-3">
                    <div className="lg:sticky lg:top-[108px]">
                      {toc.length > 1 && (
                        <nav
                          aria-labelledby="on-this-page"
                          className="rounded-2xl border border-ash-200 bg-white p-5 shadow-soft"
                        >
                          <p
                            id="on-this-page"
                            className="font-ui text-[11px] font-bold uppercase tracking-[0.12em] text-ash-400"
                          >
                            On this page
                          </p>
                          <ul className="toc-scroll mt-4 max-h-[320px] space-y-1 overflow-y-auto pr-2">
                            {toc.map((entry) => (
                              <li key={entry.id}>
                                <a
                                  href={`#${entry.id}`}
                                  onClick={(event) => jumpTo(event, entry.id)}
                                  aria-current={active === entry.id ? 'true' : undefined}
                                  className={`block border-l-2 py-1.5 pl-3.5 font-ui text-[13px] leading-[1.45] transition-colors ${
                                    active === entry.id
                                      ? 'border-brand-600 font-semibold text-brand-700'
                                      : 'border-ash-200 text-ash-500 hover:border-ash-400 hover:text-ash-800'
                                  }`}
                                >
                                  {entry.label}
                                </a>
                              </li>
                            ))}
                          </ul>
                        </nav>
                      )}

                      {/* Standing CTA, as on the reference layout */}
                      <div className="grad-brand mt-6 rounded-2xl p-6 text-white shadow-glow">
                        <p className="font-display text-[17px] font-bold leading-snug">
                          Research the archive
                        </p>
                        <p className="mt-2 font-prose text-[13px] leading-[1.65] text-white/85">
                          Ask a question in plain language and get an answer cited to the
                          judgment it came from.
                        </p>
                        <Link
                          to="/chat/new"
                          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 font-ui text-[13.5px] font-bold text-brand-700 transition-transform duration-300 hover:-translate-y-0.5"
                        >
                          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                            balance
                          </span>
                          Open the workspace
                        </Link>
                      </div>
                    </div>
                  </aside>

                  <div className="lg:col-span-8 xl:col-span-9">
                    {/* Sanitized in articleHtml.js — never inject blog.contentHtml directly. */}
                    <div
                      className="blog-prose"
                      dangerouslySetInnerHTML={{ __html: html }}
                    />

                    {blog.tags?.length > 0 && (
                      <div className="mt-12 flex flex-wrap items-center gap-2 border-t border-ash-150 pt-7">
                        <span className="mr-1 font-ui text-[11px] font-bold uppercase tracking-[0.1em] text-ash-400">
                          Topics
                        </span>
                        {blog.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-brand-50 px-3 py-1 font-ui text-[12px] font-semibold text-brand-700"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-ash-200 bg-ash-50 p-5">
                      <div className="flex items-center gap-3">
                        <img
                          src={blog.author.avatar || '/assets/user.png'}
                          alt=""
                          loading="lazy"
                          className="h-11 w-11 rounded-full border border-ash-200 object-cover"
                        />
                        <span className="font-ui text-[13.5px]">
                          <span className="block font-bold text-ash-900">
                            Written by {blog.author.name}
                          </span>
                          <span className="block text-ash-500">{blog.author.role}</span>
                        </span>
                      </div>
                      <span className="rounded-full bg-brand-50 px-3.5 py-1.5 font-ui text-[12px] font-semibold text-brand-700">
                        {blog.category}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Related ──────────────────────────────────────── */}
              {blog.related?.length > 0 && (
                <section
                  aria-label="Related articles"
                  className="border-t border-ash-150 bg-ash-50/60"
                >
                  <div className="mx-auto w-full max-w-[1200px] px-5 py-16 sm:px-8">
                    <h2 className="font-display text-[clamp(1.5rem,3vw,2rem)] font-bold tracking-[-0.025em] text-ash-900">
                      Related Articles
                    </h2>

                    <div className="mt-8 grid grid-cols-1 gap-7 md:grid-cols-2 lg:grid-cols-3">
                      {blog.related.map((other, index) => (
                        <Reveal key={other.slug} variant="up" delay={index * 70} className="h-full">
                          <BlogCard blog={other} />
                        </Reveal>
                      ))}
                    </div>

                    <div className="mt-12 text-center">
                      <Link
                        to="/blogs"
                        className="group inline-flex items-center gap-2 rounded-full border border-ash-300 bg-white px-7 py-3.5 font-ui text-[14.5px] font-semibold text-ash-800 transition-colors hover:border-brand-300 hover:text-brand-700"
                      >
                        Explore all articles
                        <span
                          aria-hidden="true"
                          className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover:translate-x-1"
                        >
                          arrow_forward
                        </span>
                      </Link>
                    </div>
                  </div>
                </section>
              )}
            </>
          )
        )}
      </main>

      <SiteFoot />
    </div>
  );
};

export default BlogDetailPage;
