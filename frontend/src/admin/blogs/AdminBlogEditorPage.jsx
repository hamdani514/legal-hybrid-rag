import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import RichTextEditor from '../../components/editor/RichTextEditor';
import { richTextToPlain } from '../../lib/richText';
import { slugify } from '../../lib/slug';
import { apiFetch } from '../../lib/api';

const BLANK = {
  title: '',
  slug: '',
  excerpt: '',
  category: 'Legal Research',
  readTime: '',
  publishedAt: '',
  status: 'published',
  isFeatured: false,
  coverImage: '',
  tags: [],
  contentHtml: '',
  author: { name: '', role: '', avatar: '' },
};

const WORDS_PER_MINUTE = 225;

/** Today in the format the articles store, e.g. "Oct 18, 2026". */
const todayLabel = () =>
  new Date().toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });

/** Read once rather than in an effect, so there is no render with a signed-in
 *  admin showing as absent. */
const readAdmin = () => {
  try {
    return JSON.parse(localStorage.getItem('currentAdmin') || 'null');
  } catch {
    return null;
  }
};

const bylineFor = (admin) => ({
  name: admin?.name || 'Verdict AI',
  role: admin?.role === 'super_admin' ? 'Editor' : 'Contributor',
  avatar: admin?.avatar_url || '',
});

const field =
  'w-full rounded-xl border border-ash-200 bg-white px-3.5 py-2.5 font-prose text-[14px] text-ash-900 transition-colors focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100';

const label = 'mb-1.5 block font-ui text-[12.5px] font-semibold text-ash-700';

/**
 * Write or edit one article.
 *
 * The body is the rich-text editor; everything else is the card metadata the
 * hub and the article header render. The editor keeps its own document and
 * hands back normalized HTML at save time via its ref, so this page does not
 * re-render the editable surface on every keystroke.
 */
const AdminBlogEditorPage = () => {
  const { slug } = useParams();
  const navigate = useNavigate();
  const editorRef = useRef(null);

  const isNew = !slug;
  const [currentAdmin] = useState(readAdmin);
  const [form, setForm] = useState(() =>
    // A new article is bylined to whoever is writing it, until changed.
    isNew ? { ...BLANK, author: bylineFor(readAdmin()) } : BLANK
  );
  // Whether the author has taken the slug over. A new article's slug tracks
  // the title until they edit it; an existing one never moves on its own,
  // because that would change a URL people may already have.
  const [slugTouched, setSlugTouched] = useState(!isNew);
  const isDraft = form.status === 'draft';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!currentAdmin) navigate('/admin-login');
  }, [currentAdmin, navigate]);

  useEffect(() => {
    if (isNew) return undefined;
    let cancelled = false;

    (async () => {
      try {
        const response = await apiFetch(`/api/admin/blogs/${encodeURIComponent(slug)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || 'Failed to load the article.');
        if (!cancelled) setForm({ ...BLANK, ...data });
      } catch (caught) {
        if (!cancelled) setError(caught.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [slug, isNew]);

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  /** Typing the title also writes the slug, until the author edits it. */
  const setTitle = (title) =>
    setForm((current) => ({
      ...current,
      title,
      slug: slugTouched ? current.slug : slugify(title),
    }));

  const setAuthor = (key, value) =>
    setForm((current) => ({ ...current, author: { ...current.author, [key]: value } }));

  /** Read time, from the body the author has actually written. */
  const estimateReadTime = () => {
    const html = editorRef.current?.getHTML() || form.contentHtml;
    const words = richTextToPlain(html).split(/\s+/).filter(Boolean).length;
    set('readTime', `${Math.max(1, Math.round(words / WORDS_PER_MINUTE))} min read`);
  };

  /** Excerpt, from the opening of the body, when the author has not written one. */
  const deriveExcerpt = () => {
    const html = editorRef.current?.getHTML() || form.contentHtml;
    const text = richTextToPlain(html);
    set('excerpt', text.length > 220 ? `${text.slice(0, 217).trimEnd()}…` : text);
  };

  const save = async () => {
    setError('');
    setNotice('');

    if (!form.title.trim()) {
      setError('An article needs a title.');
      return;
    }

    // The editor owns the live document; ask it rather than trusting the last
    // onChange, so a save immediately after typing cannot miss the final edit.
    const contentHtml = editorRef.current?.getHTML() ?? form.contentHtml;

    const payload = {
      ...form,
      contentHtml,
      tags: (Array.isArray(form.tags) ? form.tags : [])
        .map((tag) => String(tag).trim())
        .filter(Boolean),
      author: {
        name: form.author.name || 'Verdict AI',
        role: form.author.role || 'Editorial',
        avatar: form.author.avatar || '',
      },
    };

    setSaving(true);
    try {
      const response = await apiFetch(
        isNew ? '/api/admin/blogs' : `/api/admin/blogs/${encodeURIComponent(slug)}`,
        {
          method: isNew ? 'POST' : 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Save failed.');

      setForm({ ...BLANK, ...data });
      setNotice('Saved.');

      // A new article, or a renamed one, lives at a different URL now.
      if (data.slug !== slug) navigate(`/admin/blogs/${data.slug}/edit`, { replace: true });
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-ash-50">
      <AdminSidebar activeRoute="blogs" currentAdmin={currentAdmin} />

      <div className="ml-72">
        <header className="sticky top-0 z-40 flex flex-wrap items-center justify-between gap-4 border-b border-ash-200 bg-ash-50/90 px-8 py-5 backdrop-blur-lg">
          <div className="min-w-0">
            <Link
              to="/admin/blogs"
              className="inline-flex items-center gap-1.5 font-ui text-[12.5px] font-semibold text-ash-500 hover:text-brand-700"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                arrow_back
              </span>
              All articles
            </Link>
            <div className="mt-1 flex items-center gap-2.5">
              <h1 className="truncate font-display text-[1.6rem] font-bold tracking-[-0.03em] text-ash-900">
                {isNew ? 'New article' : form.title || 'Edit article'}
              </h1>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 font-ui text-[10.5px] font-bold uppercase tracking-[0.08em] ${
                  isDraft ? 'bg-amber-400/20 text-gold-700' : 'bg-mint-500/15 text-mint-700'
                }`}
              >
                {isDraft ? 'Draft' : 'Published'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {notice && <span className="font-ui text-[13px] font-semibold text-mint-600">{notice}</span>}
            {/* A draft has no public page, so Preview would only ever show the
                "Article unavailable" screen. */}
            {!isNew && !isDraft && (
              <a
                href={`/blogs/${form.slug}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl border border-ash-300 bg-white px-4 py-2.5 font-ui text-[13.5px] font-semibold text-ash-700 hover:bg-ash-100"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                  visibility
                </span>
                Preview
              </a>
            )}
            <button
              type="button"
              onClick={save}
              disabled={saving || loading}
              className="grad-btn inline-flex items-center gap-2 rounded-xl px-6 py-2.5 font-ui text-[13.5px] font-bold text-white shadow-glow disabled:opacity-60"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                {saving ? 'progress_activity' : 'save'}
              </span>
              {saving ? 'Saving…' : isDraft ? 'Save draft' : 'Save & publish'}
            </button>
          </div>
        </header>

        <main className="p-8">
          {error && (
            <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 font-ui text-[13.5px] text-rose-700">
              {error}
            </div>
          )}

          {loading ? (
            <p className="py-20 text-center font-ui text-[14px] text-ash-500">Loading article…</p>
          ) : (
            <div className="grid grid-cols-1 gap-7 xl:grid-cols-12">
              {/* ── Body ───────────────────────────────────────────── */}
              <div className="xl:col-span-8">
                <label className={label} htmlFor="blog-title">
                  Title
                </label>
                <input
                  id="blog-title"
                  type="text"
                  value={form.title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="How to…"
                  className={`${field} !text-[18px] !font-semibold`}
                />

                {/* ── Description ──────────────────────────────────── */}
                <div className="mt-5">
                  <div className="flex items-center justify-between">
                    <label className={label} htmlFor="blog-excerpt">
                      Description
                    </label>
                    <button
                      type="button"
                      onClick={deriveExcerpt}
                      className="mb-1.5 font-ui text-[11.5px] font-semibold text-brand-600 hover:text-brand-800"
                    >
                      Use opening lines
                    </button>
                  </div>
                  <textarea
                    id="blog-excerpt"
                    rows={2}
                    value={form.excerpt}
                    onChange={(event) => set('excerpt', event.target.value)}
                    placeholder="One or two sentences. Shown under the title and on the article card."
                    className={`${field} resize-y`}
                  />
                </div>

                {/* ── Slug / date / status ─────────────────────────── */}
                <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <div className="flex items-center justify-between">
                      <label className={label} htmlFor="blog-slug">
                        URL slug
                      </label>
                      {/* Retyping the title of a LIVE article must not silently
                          move its public URL, so an existing article only
                          re-syncs when the author asks for it. */}
                      {!isNew && (
                        <button
                          type="button"
                          onClick={() => {
                            setSlugTouched(true);
                            set('slug', slugify(form.title));
                          }}
                          className="mb-1.5 font-ui text-[11.5px] font-semibold text-brand-600 hover:text-brand-800"
                        >
                          Sync from title
                        </button>
                      )}
                    </div>
                    <input
                      id="blog-slug"
                      type="text"
                      value={form.slug}
                      onChange={(event) => {
                        setSlugTouched(true);
                        set('slug', event.target.value);
                      }}
                      placeholder="generated from the title"
                      className={`${field} font-mono !text-[13px]`}
                    />
                    <span className="mt-1 block truncate font-prose text-[11.5px] text-ash-500">
                      /blogs/{form.slug || slugify(form.title) || '…'}
                    </span>
                  </div>

                  <div>
                    <label className={label} htmlFor="blog-published">
                      Date
                    </label>
                    <input
                      id="blog-published"
                      type="text"
                      value={form.publishedAt}
                      onChange={(event) => set('publishedAt', event.target.value)}
                      placeholder={todayLabel()}
                      className={field}
                    />
                    <span className="mt-1 block font-prose text-[11.5px] text-ash-500">
                      Format: {todayLabel()}. Also sets the ordering on the hub.
                    </span>
                  </div>
                </div>

                {/* ── Publish or draft ─────────────────────────────── */}
                <fieldset className="mt-5 rounded-2xl border border-ash-200 bg-white p-4">
                  <legend className="px-1.5 font-ui text-[12.5px] font-semibold text-ash-700">
                    Visibility
                  </legend>
                  <div className="flex flex-wrap gap-2.5">
                    {[
                      {
                        value: 'published',
                        icon: 'public',
                        title: 'Published',
                        hint: 'Live on the site for everyone.',
                      },
                      {
                        value: 'draft',
                        icon: 'edit_note',
                        title: 'Draft',
                        hint: 'Saved here only. Not shown to users.',
                      },
                    ].map((option) => {
                      const active = form.status === option.value;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          aria-pressed={active}
                          onClick={() => set('status', option.value)}
                          className={`flex flex-1 items-start gap-2.5 rounded-xl border p-3 text-left transition-colors ${
                            active
                              ? 'border-brand-400 bg-brand-50 ring-2 ring-brand-100'
                              : 'border-ash-200 bg-white hover:border-ash-300'
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className={`material-symbols-outlined text-[20px] ${
                              active ? 'text-brand-600' : 'text-ash-400'
                            }`}
                          >
                            {option.icon}
                          </span>
                          <span>
                            <span
                              className={`block font-ui text-[13.5px] font-bold ${
                                active ? 'text-brand-800' : 'text-ash-800'
                              }`}
                            >
                              {option.title}
                            </span>
                            <span className="block font-prose text-[11.5px] text-ash-500">
                              {option.hint}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </fieldset>

                <span className={`${label} mt-5`}>Article body</span>
                <RichTextEditor
                  ref={editorRef}
                  value={form.contentHtml}
                  onChange={(html) => set('contentHtml', html)}
                  placeholder="Write the article. Use Heading 2 for the sections that appear in the contents rail."
                />
                <p className="mt-2 font-prose text-[12px] text-ash-500">
                  Each <strong>Heading 2</strong> becomes an entry in the article page&rsquo;s
                  &ldquo;On this page&rdquo; rail.
                </p>
              </div>

              {/* ── Metadata ───────────────────────────────────────── */}
              <aside className="space-y-5 xl:col-span-4">
                <section className="rounded-2xl border border-ash-200 bg-white p-5 shadow-soft">
                  <h2 className="mb-4 font-display text-[15px] font-bold text-ash-900">Publishing</h2>

                  <div className="space-y-4">
                    <div>
                      <label className={label} htmlFor="blog-category">
                        Category
                      </label>
                      <input
                        id="blog-category"
                        type="text"
                        value={form.category}
                        onChange={(event) => set('category', event.target.value)}
                        className={field}
                      />
                    </div>

                    <div>
                      <div>
                        <label className={label} htmlFor="blog-readtime">
                          Read time
                        </label>
                        <div className="flex gap-1.5">
                          <input
                            id="blog-readtime"
                            type="text"
                            value={form.readTime}
                            onChange={(event) => set('readTime', event.target.value)}
                            placeholder="5 min read"
                            className={field}
                          />
                          <button
                            type="button"
                            onClick={estimateReadTime}
                            title="Estimate from the article body"
                            className="shrink-0 rounded-xl border border-ash-300 px-2.5 text-ash-600 hover:bg-ash-100"
                          >
                            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                              timer
                            </span>
                          </button>
                        </div>
                      </div>
                    </div>

                    <label className="flex items-center gap-2.5 pt-1">
                      <input
                        type="checkbox"
                        checked={form.isFeatured}
                        onChange={(event) => set('isFeatured', event.target.checked)}
                        className="h-4 w-4 rounded border-ash-300 text-brand-600"
                      />
                      <span className="font-ui text-[13px] text-ash-700">
                        Feature at the top of the hub
                      </span>
                    </label>
                  </div>
                </section>

                <section className="rounded-2xl border border-ash-200 bg-white p-5 shadow-soft">
                  <h2 className="mb-4 font-display text-[15px] font-bold text-ash-900">Card</h2>

                  <div className="space-y-4">
                    {/* The description lives with the title, where it is
                        written — this panel is only the card's imagery. */}
                    <div>
                      <label className={label} htmlFor="blog-cover">
                        Cover image URL
                      </label>
                      <input
                        id="blog-cover"
                        type="text"
                        value={form.coverImage}
                        onChange={(event) => set('coverImage', event.target.value)}
                        placeholder="https://"
                        className={field}
                      />
                      {form.coverImage && (
                        <img
                          src={form.coverImage}
                          alt=""
                          className="mt-2.5 h-28 w-full rounded-xl border border-ash-200 bg-ash-100 object-cover"
                        />
                      )}
                    </div>

                    <div>
                      <label className={label} htmlFor="blog-tags">
                        Tags
                      </label>
                      <input
                        id="blog-tags"
                        type="text"
                        value={(form.tags || []).join(', ')}
                        onChange={(event) => set('tags', event.target.value.split(','))}
                        placeholder="evidence, procedure, appeals"
                        className={field}
                      />
                      <span className="mt-1 block font-prose text-[11.5px] text-ash-500">
                        Comma separated. Used by the hub search.
                      </span>
                    </div>
                  </div>
                </section>

                <section className="rounded-2xl border border-ash-200 bg-white p-5 shadow-soft">
                  <h2 className="mb-4 font-display text-[15px] font-bold text-ash-900">Byline</h2>

                  <div className="space-y-4">
                    <div>
                      <label className={label} htmlFor="blog-author">
                        Name
                      </label>
                      <input
                        id="blog-author"
                        type="text"
                        value={form.author.name}
                        onChange={(event) => setAuthor('name', event.target.value)}
                        className={field}
                      />
                    </div>
                    <div>
                      <label className={label} htmlFor="blog-author-role">
                        Role
                      </label>
                      <input
                        id="blog-author-role"
                        type="text"
                        value={form.author.role}
                        onChange={(event) => setAuthor('role', event.target.value)}
                        placeholder="Legal Research Editor"
                        className={field}
                      />
                    </div>
                    <div>
                      <label className={label} htmlFor="blog-author-avatar">
                        Avatar URL
                      </label>
                      <input
                        id="blog-author-avatar"
                        type="text"
                        value={form.author.avatar}
                        onChange={(event) => setAuthor('avatar', event.target.value)}
                        placeholder="https://"
                        className={field}
                      />
                    </div>
                  </div>
                </section>
              </aside>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default AdminBlogEditorPage;
