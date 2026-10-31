import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';
import BlogCard from '../../blogs/BlogCard';
import { apiFetch } from '../../../lib/api';

const RECENT_COUNT = 3;

/**
 * The newest articles from the insights hub, as cards, with a link to the
 * whole archive.
 *
 * GET /api/blogs already returns articles newest-first, so this takes the
 * first RECENT_COUNT. The cards are the hub's own BlogCard, so the two pages
 * never drift apart.
 *
 * A home page should not show an error box for a secondary section: if the
 * request fails, or there are no articles yet, the section is left out.
 */
const CardSkeleton = () => (
  <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft" aria-hidden="true">
    <div className="h-48 animate-pulse bg-ash-100" />
    <div className="flex flex-1 flex-col gap-3 p-6">
      <div className="h-3 w-1/3 animate-pulse rounded bg-ash-100" />
      <div className="h-5 w-4/5 animate-pulse rounded bg-ash-100" />
      <div className="h-3 w-full animate-pulse rounded bg-ash-100" />
      <div className="h-3 w-2/3 animate-pulse rounded bg-ash-100" />
    </div>
  </div>
);

const RecentBlogs = ({ count = RECENT_COUNT }) => {
  const [blogs, setBlogs] = useState([]);
  const [state, setState] = useState('loading'); // 'loading' | 'ready' | 'hidden'

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await apiFetch('/api/blogs');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const recent = (Array.isArray(data) ? data : []).slice(0, count);
        if (cancelled) return;
        setBlogs(recent);
        setState(recent.length ? 'ready' : 'hidden');
      } catch {
        if (!cancelled) setState('hidden');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [count]);

  if (state === 'hidden') return null;

  return (
    <section aria-labelledby="recent-blogs-title" className="ground-tint w-full px-5 py-12 sm:px-8 md:py-16">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Insights"
          icon="article"
          title={<span id="recent-blogs-title">Latest from the blog.</span>}
          accent="Notes on the law and the archive."
          lede="Commentary on recent Supreme Court judgments, research technique, and how Verdict AI reads the reported decisions."
          className="mx-auto"
        />

        <div className="mt-10 grid grid-cols-1 gap-7 md:mt-12 md:grid-cols-2 lg:grid-cols-3">
          {state === 'loading'
            ? Array.from({ length: count }, (_, i) => <CardSkeleton key={i} />)
            : blogs.map((blog, index) => (
                <Reveal key={blog.slug} delay={index * 90} className="h-full">
                  <BlogCard blog={blog} />
                </Reveal>
              ))}
        </div>

        <div className="mt-12 flex justify-center">
          <Link
            to="/blogs"
            className="inline-flex items-center gap-2 rounded-full border border-ash-300 bg-white px-6 py-3 font-ui text-[14px] font-bold text-ash-800 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
          >
            View all articles
            <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
          </Link>
        </div>
      </div>
    </section>
  );
};

export default RecentBlogs;
