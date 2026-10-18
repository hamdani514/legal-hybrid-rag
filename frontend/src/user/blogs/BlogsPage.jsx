import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import Reveal from '../components/Reveal';
import BlogCard from './BlogCard';
import { apiFetch } from '../../lib/api';

const ARTICLES_PER_PAGE = 6;

/**
 * Insights hub: the featured article, then a searchable, paginated grid.
 *
 * Articles arrive from GET /api/blogs already ordered newest-first, so this
 * page never sorts — it only filters. Search runs in the browser because the
 * whole collection is one small request; move it server-side if the archive
 * ever outgrows a single page load.
 *
 * Posts are keyed by `slug`, not by id: the slug is the unique public URL and
 * the one field the detail route needs.
 */
const BlogsPage = () => {
  const [blogs, setBlogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await apiFetch('/api/blogs');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (!cancelled) setBlogs(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) setError('We could not load the insights archive just now.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const searching = query.trim().length > 0;

  const featured = useMemo(
    () => blogs.find((blog) => blog.isFeatured) || blogs[0] || null,
    [blogs]
  );

  const listed = useMemo(() => {
    const needle = query.trim().toLowerCase();

    // While searching, the featured article is a candidate like any other —
    // hiding it would make a direct title search return nothing.
    const pool = needle
      ? blogs
      : blogs.filter((blog) => blog.slug !== featured?.slug);

    if (!needle) return pool;

    return pool.filter((blog) =>
      [blog.title, blog.excerpt, blog.category, ...(blog.tags || [])]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    );
  }, [blogs, featured, query]);

  const totalPages = Math.max(1, Math.ceil(listed.length / ARTICLES_PER_PAGE));

  // A shrinking result set can leave `page` past the end, which would read as
  // an empty archive rather than as a filter. Clamped on render rather than
  // corrected in an effect, so there is no second render to see.
  const currentPage = Math.min(page, totalPages);

  const visible = useMemo(() => {
    const start = (currentPage - 1) * ARTICLES_PER_PAGE;
    return listed.slice(start, start + ARTICLES_PER_PAGE);
  }, [listed, currentPage]);

  const onSearch = (value) => {
    setQuery(value);
    setPage(1);
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main id="main-content" className="w-full flex-1">
        {/* ── Masthead ─────────────────────────────────────────────── */}
        <header className="ground-light relative w-full overflow-hidden">
          <div className="relative z-[1] mx-auto w-full max-w-[1200px] px-5 pb-16 pt-32 text-center sm:px-8 sm:pt-36">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold uppercase tracking-[0.08em] text-brand-700">
              <span aria-hidden="true" className="material-symbols-outlined text-[17px]">
                article
              </span>
              Insights &amp; Method Notes
            </span>

            <h1 className="mx-auto mt-7 max-w-[46rem] font-display text-[clamp(2.25rem,5.4vw,3.5rem)] font-bold leading-[1.06] tracking-[-0.035em] text-ash-900">
              Document guides &amp;{' '}
              <span className="grad-text">research practice</span>
            </h1>

            <p className="mx-auto mt-6 max-w-[40rem] font-prose text-[1.0625rem] leading-[1.8] text-ash-600">
              Working notes on document review, file security, OCR and the retrieval
              machinery behind the archive — written for the people who do the reading.
            </p>

            {/* Search */}
            <div className="relative mx-auto mt-9 max-w-xl">
              <span
                aria-hidden="true"
                className="material-symbols-outlined pointer-events-none absolute inset-y-0 left-4 flex items-center text-[21px] text-ash-400"
              >
                search
              </span>
              <input
                type="search"
                value={query}
                onChange={(event) => onSearch(event.target.value)}
                placeholder="Search by topic, keyword or tag..."
                aria-label="Search articles"
                className="w-full rounded-full border border-ash-200 bg-white py-4 pl-12 pr-4 font-prose text-[15px] text-ash-900 shadow-soft transition-colors placeholder:text-ash-400 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100"
              />
            </div>
          </div>
        </header>

        {/* ── Featured ─────────────────────────────────────────────── */}
        {!searching && featured && !loading && (
          <section
            aria-label="Featured article"
            className="mx-auto w-full max-w-[1200px] px-5 pb-16 sm:px-8"
          >
            <Reveal variant="rise">
              <article className="grid grid-cols-1 overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-card transition-shadow duration-300 hover:shadow-card-lg lg:grid-cols-12">
                <Link
                  to={`/blogs/${featured.slug}`}
                  className="group relative block min-h-[280px] overflow-hidden bg-ash-100 lg:col-span-5"
                >
                  {featured.coverImage && (
                    <img
                      src={featured.coverImage}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
                    />
                  )}
                  <span className="absolute left-4 top-4 rounded-full bg-ink-900/70 px-3.5 py-1.5 font-ui text-[11px] font-bold uppercase tracking-[0.1em] text-white backdrop-blur-sm">
                    Featured
                  </span>
                </Link>

                <div className="flex flex-col justify-between gap-8 p-7 sm:p-10 lg:col-span-7">
                  <div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 font-ui text-[12.5px] text-ash-500">
                      <span className="rounded-full bg-brand-50 px-3 py-1 font-semibold text-brand-700">
                        {featured.category}
                      </span>
                      <span>{featured.publishedAt}</span>
                      <span aria-hidden="true" className="text-ash-300">
                        ·
                      </span>
                      <span>{featured.readTime}</span>
                    </div>

                    <h2 className="mt-5 font-display text-[clamp(1.5rem,2.6vw,2rem)] font-bold leading-[1.18] tracking-[-0.02em] text-ash-900">
                      <Link
                        to={`/blogs/${featured.slug}`}
                        className="transition-colors hover:text-brand-700"
                      >
                        {featured.title}
                      </Link>
                    </h2>

                    <p className="mt-4 font-prose text-[15.5px] leading-[1.75] text-ash-600">
                      {featured.excerpt}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-4 border-t border-ash-150 pt-6">
                    <div className="flex items-center gap-3">
                      <img
                        src={featured.author.avatar || '/assets/user.png'}
                        alt=""
                        loading="lazy"
                        className="h-10 w-10 rounded-full border border-ash-200 object-cover"
                      />
                      <span className="font-ui text-[13.5px] font-semibold text-ash-900">
                        {featured.author.name}
                        <span className="block font-normal text-ash-500">
                          {featured.author.role}
                        </span>
                      </span>
                    </div>

                    <Link
                      to={`/blogs/${featured.slug}`}
                      className="group inline-flex items-center gap-2 font-ui text-[14px] font-bold text-brand-700 transition-colors hover:text-brand-800"
                    >
                      Read the guide
                      <span
                        aria-hidden="true"
                        className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover:translate-x-1"
                      >
                        arrow_forward
                      </span>
                    </Link>
                  </div>
                </div>
              </article>
            </Reveal>
          </section>
        )}

        {/* ── Grid ─────────────────────────────────────────────────── */}
        <section
          aria-label={searching ? 'Search results' : 'Latest articles'}
          className="mx-auto w-full max-w-[1200px] px-5 pb-24 sm:px-8"
        >
          <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
            <h2 className="font-display text-[clamp(1.5rem,3vw,2rem)] font-bold tracking-[-0.025em] text-ash-900">
              {searching ? 'Search results' : 'Latest articles'}
            </h2>
            {!loading && !error && (
              <span className="font-ui text-[13px] font-medium text-ash-500">
                {listed.length} {listed.length === 1 ? 'article' : 'articles'}
                {totalPages > 1 && ` · page ${currentPage} of ${totalPages}`}
              </span>
            )}
          </div>

          {loading ? (
            <div
              role="status"
              aria-live="polite"
              className="grid grid-cols-1 gap-7 md:grid-cols-2 lg:grid-cols-3"
            >
              <span className="sr-only">Loading articles</span>
              {Array.from({ length: 3 }, (_, index) => (
                <div
                  key={index}
                  className="animate-pulse overflow-hidden rounded-3xl border border-ash-200 bg-white"
                >
                  <div className="h-48 w-full bg-ash-100" />
                  <div className="space-y-3 p-6">
                    <div className="h-3 w-24 rounded bg-ash-100" />
                    <div className="h-4 w-full rounded bg-ash-100" />
                    <div className="h-4 w-3/4 rounded bg-ash-100" />
                  </div>
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="rounded-3xl border border-ash-200 bg-ash-50 p-12 text-center">
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[32px] text-ash-400"
              >
                cloud_off
              </span>
              <p className="mt-3 font-ui text-[15.5px] font-semibold text-ash-800">{error}</p>
              <button
                type="button"
                onClick={() => setReloadKey((key) => key + 1)}
                className="mt-6 rounded-full border border-ash-300 bg-white px-6 py-2.5 font-ui text-[14px] font-semibold text-ash-800 transition-colors hover:border-brand-300 hover:text-brand-700"
              >
                Try again
              </button>
            </div>
          ) : visible.length === 0 ? (
            <div className="rounded-3xl border border-ash-200 bg-ash-50 p-12 text-center">
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[32px] text-ash-400"
              >
                search_off
              </span>
              <p className="mt-3 font-ui text-[15.5px] font-semibold text-ash-800">
                {searching ? `Nothing matched “${query.trim()}”` : 'No articles published yet'}
              </p>
              {searching && (
                <button
                  type="button"
                  onClick={() => onSearch('')}
                  className="mt-6 rounded-full border border-ash-300 bg-white px-6 py-2.5 font-ui text-[14px] font-semibold text-ash-800 transition-colors hover:border-brand-300 hover:text-brand-700"
                >
                  Clear search
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-7 md:grid-cols-2 lg:grid-cols-3">
              {visible.map((blog, index) => (
                // Each card reveals itself, so the cascade comes from its own
                // delay — Reveal's `stagger` sets a variable on children that
                // carry no reveal styles of their own.
                <Reveal key={blog.slug} variant="up" delay={index * 70} className="h-full">
                  <BlogCard blog={blog} />
                </Reveal>
              ))}
            </div>
          )}

          {/* ── Pagination ─────────────────────────────────────────── */}
          {!loading && !error && totalPages > 1 && (
            <nav
              aria-label="Article pages"
              className="mt-14 flex items-center justify-center gap-2"
            >
              <button
                type="button"
                onClick={() => setPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                aria-label="Previous page"
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-ash-200 bg-white font-ui text-ash-700 transition-colors hover:border-brand-300 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-ash-200 disabled:hover:text-ash-700"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
                  chevron_left
                </span>
              </button>

              {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => (
                <button
                  key={number}
                  type="button"
                  onClick={() => setPage(number)}
                  aria-current={currentPage === number ? 'page' : undefined}
                  aria-label={`Page ${number}`}
                  className={`h-10 w-10 rounded-xl font-ui text-[14px] font-bold transition-colors ${
                    currentPage === number
                      ? 'grad-btn text-white shadow-glow'
                      : 'border border-ash-200 bg-white text-ash-700 hover:border-brand-300 hover:text-brand-700'
                  }`}
                >
                  {number}
                </button>
              ))}

              <button
                type="button"
                onClick={() => setPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                aria-label="Next page"
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-ash-200 bg-white font-ui text-ash-700 transition-colors hover:border-brand-300 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-ash-200 disabled:hover:text-ash-700"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
                  chevron_right
                </span>
              </button>
            </nav>
          )}
        </section>
      </main>

      <SiteFoot />
    </div>
  );
};

export default BlogsPage;
