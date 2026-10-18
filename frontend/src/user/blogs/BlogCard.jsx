import { Link } from 'react-router-dom';

/**
 * One article card. Shared by the hub grid and the "Related articles" row so
 * the two never drift apart.
 *
 * The cover is a second route to the same article: skipped in the tab order so
 * keyboard users meet the title link once, but left readable so the category
 * and read-time badges are still announced.
 */
const BlogCard = ({ blog }) => (
  <article className="group flex h-full flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft transition-all duration-300 hover:-translate-y-1 hover:shadow-card">
    <Link
      to={`/blogs/${blog.slug}`}
      tabIndex={-1}
      className="relative block h-48 overflow-hidden bg-ash-100"
    >
      {blog.coverImage && (
        <img
          src={blog.coverImage}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.05]"
        />
      )}
      <span className="absolute left-3.5 top-3.5 rounded-full bg-ink-900/70 px-3 py-1 font-ui text-[10.5px] font-bold uppercase tracking-[0.1em] text-white backdrop-blur-sm">
        {blog.category}
      </span>
      <span className="absolute right-3.5 top-3.5 rounded-full bg-ink-900/70 px-3 py-1 font-ui text-[10.5px] font-medium text-white backdrop-blur-sm">
        {blog.readTime}
      </span>
    </Link>

    <div className="flex flex-1 flex-col p-6">
      <div className="font-ui text-[12px] font-medium text-ash-500">
        {blog.author.name} · {blog.publishedAt}
      </div>

      <h3 className="mt-2.5 font-display text-[17.5px] font-bold leading-[1.3] tracking-[-0.015em] text-ash-900">
        <Link
          to={`/blogs/${blog.slug}`}
          className="line-clamp-2 transition-colors group-hover:text-brand-700"
        >
          {blog.title}
        </Link>
      </h3>

      <p className="mt-3 line-clamp-3 font-prose text-[14px] leading-[1.7] text-ash-600">
        {blog.excerpt}
      </p>

      <div className="mt-6 flex items-center justify-between border-t border-ash-150 pt-5">
        <span className="font-ui text-[13.5px] font-bold text-brand-700">Read Insight</span>
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-50 text-brand-700 transition-colors group-hover:bg-brand-600 group-hover:text-white"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
        </span>
      </div>
    </div>
  </article>
);

export default BlogCard;
