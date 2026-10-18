import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminDeleteModal from '../components/AdminDeleteModal';
import { apiFetch } from '../../lib/api';

/** The article list: what exists, and the way in to the editor. */
/** The stored admin, read once rather than in an effect, so there is no render
 *  with a signed-in admin showing as absent. */
const readAdmin = () => {
  try {
    return JSON.parse(localStorage.getItem('currentAdmin') || 'null');
  } catch {
    return null;
  }
};

const AdminBlogsPage = () => {
  const [currentAdmin] = useState(readAdmin);
  const [blogs, setBlogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (!currentAdmin) navigate('/admin-login');
  }, [currentAdmin, navigate]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const response = await apiFetch('/api/admin/blogs');
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || 'Failed to load articles.');
        if (!cancelled) {
          setBlogs(Array.isArray(data) ? data : []);
          setError('');
        }
      } catch (caught) {
        if (!cancelled) setError(caught.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const load = useCallback(() => setReloadKey((key) => key + 1), []);

  const remove = async () => {
    if (!pendingDelete) return;
    try {
      const response = await apiFetch(`/api/admin/blogs/${encodeURIComponent(pendingDelete.slug)}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data?.detail || 'Delete failed.');
      }
      setPendingDelete(null);
      load();
    } catch (caught) {
      setError(caught.message);
      setPendingDelete(null);
    }
  };

  const needle = search.trim().toLowerCase();
  const matchesSearch = (blog) =>
    !needle ||
    [blog.title, blog.category, blog.slug, ...(blog.tags || [])]
      .join(' ')
      .toLowerCase()
      .includes(needle);

  // A draft has no status field on articles written before drafts existed,
  // so "published" is anything that is not explicitly a draft.
  const matchesStatus = (blog) =>
    statusFilter === 'all' ||
    (statusFilter === 'draft' ? blog.status === 'draft' : blog.status !== 'draft');

  const visible = blogs.filter((blog) => matchesSearch(blog) && matchesStatus(blog));
  const draftCount = blogs.filter((blog) => blog.status === 'draft').length;

  return (
    <div className="min-h-screen bg-ash-50">
      <AdminSidebar activeRoute="blogs" currentAdmin={currentAdmin} />

      <div className="ml-72">
        <AdminHeader title="Blog Articles" subtitle="Write and publish the Insights hub" />

        <main className="p-8">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
            <div className="relative max-w-sm flex-1">
              <span
                aria-hidden="true"
                className="material-symbols-outlined pointer-events-none absolute inset-y-0 left-3 flex items-center text-[20px] text-ash-400"
              >
                search
              </span>
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by title, slug, category or tag"
                aria-label="Search articles"
                className="w-full rounded-xl border border-ash-200 bg-white py-2.5 pl-10 pr-3 font-prose text-[14px] text-ash-900 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100"
              />
            </div>

            <div className="flex items-center gap-1 rounded-xl border border-ash-200 bg-white p-1">
              {[
                { value: 'all', label: `All (${blogs.length})` },
                { value: 'published', label: `Published (${blogs.length - draftCount})` },
                { value: 'draft', label: `Drafts (${draftCount})` },
              ].map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={statusFilter === option.value}
                  onClick={() => setStatusFilter(option.value)}
                  className={`rounded-lg px-3 py-1.5 font-ui text-[12.5px] font-semibold transition-colors ${
                    statusFilter === option.value
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-ash-500 hover:text-ash-800'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <Link
              to="/admin/blogs/new"
              className="grad-btn inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-ui text-[13.5px] font-bold text-white shadow-glow"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                add
              </span>
              New article
            </Link>
          </div>

          {error && (
            <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 font-ui text-[13.5px] text-rose-700">
              {error}
            </div>
          )}

          <div className="overflow-hidden rounded-2xl border border-ash-200 bg-white shadow-soft">
            {loading ? (
              <p className="p-10 text-center font-ui text-[14px] text-ash-500">Loading articles…</p>
            ) : visible.length === 0 ? (
              <div className="p-12 text-center">
                <span aria-hidden="true" className="material-symbols-outlined text-[32px] text-ash-400">
                  article
                </span>
                <p className="mt-3 font-ui text-[15px] font-semibold text-ash-800">
                  {needle ? `Nothing matched “${search.trim()}”` : 'No articles yet'}
                </p>
                {!needle && (
                  <Link
                    to="/admin/blogs/new"
                    className="mt-5 inline-block rounded-xl border border-ash-300 bg-white px-5 py-2.5 font-ui text-[13.5px] font-semibold text-ash-800 hover:border-brand-300 hover:text-brand-700"
                  >
                    Write the first one
                  </Link>
                )}
              </div>
            ) : (
              <table className="w-full text-left">
                <thead className="border-b border-ash-200 bg-ash-50">
                  <tr className="font-ui text-[11.5px] font-bold uppercase tracking-[0.08em] text-ash-500">
                    <th className="px-5 py-3.5">Article</th>
                    <th className="px-5 py-3.5">Category</th>
                    <th className="px-5 py-3.5">Published</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((blog) => (
                    <tr key={blog.slug} className="border-b border-ash-150 last:border-0 hover:bg-ash-50/60">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-11 w-16 shrink-0 overflow-hidden rounded-lg border border-ash-200 bg-ash-100">
                            {blog.coverImage && (
                              <img
                                src={blog.coverImage}
                                alt=""
                                loading="lazy"
                                className="h-full w-full object-cover"
                              />
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="truncate font-ui text-[14px] font-semibold text-ash-900">
                                {blog.title}
                              </span>
                              {blog.status === 'draft' && (
                                <span className="shrink-0 rounded-full bg-amber-400/20 px-2 py-0.5 font-ui text-[10px] font-bold uppercase tracking-wider text-gold-700">
                                  Draft
                                </span>
                              )}
                              {blog.isFeatured && (
                                <span className="shrink-0 rounded-full bg-gold-100 px-2 py-0.5 font-ui text-[10px] font-bold uppercase tracking-wider text-gold-700">
                                  Featured
                                </span>
                              )}
                            </div>
                            <span className="block truncate font-mono text-[11.5px] text-ash-500">
                              /blogs/{blog.slug}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className="rounded-full bg-brand-50 px-2.5 py-1 font-ui text-[11.5px] font-semibold text-brand-700">
                          {blog.category}
                        </span>
                      </td>
                      <td className="px-5 py-4 font-ui text-[13px] text-ash-600">{blog.publishedAt}</td>
                      <td className="px-5 py-4">
                        <div className="flex items-center justify-end gap-1">
                          <a
                            href={`/blogs/${blog.slug}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="View on the site"
                            className="flex h-8 w-8 items-center justify-center rounded-lg text-ash-500 hover:bg-ash-100 hover:text-ash-900"
                          >
                            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                              open_in_new
                            </span>
                          </a>
                          <Link
                            to={`/admin/blogs/${blog.slug}/edit`}
                            title="Edit"
                            className="flex h-8 w-8 items-center justify-center rounded-lg text-brand-600 hover:bg-brand-50"
                          >
                            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                              edit
                            </span>
                          </Link>
                          <button
                            type="button"
                            title="Delete"
                            onClick={() => setPendingDelete(blog)}
                            className="flex h-8 w-8 items-center justify-center rounded-lg text-rose-600 hover:bg-rose-50"
                          >
                            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                              delete
                            </span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {!loading && visible.length > 0 && (
            <p className="mt-4 font-ui text-[12.5px] text-ash-500">
              {visible.length} of {blogs.length} {blogs.length === 1 ? 'article' : 'articles'}
            </p>
          )}
        </main>
      </div>

      {pendingDelete && (
        <AdminDeleteModal
          isOpen
          title="Delete this article?"
          message={`“${pendingDelete.title}” will be removed from the site. This cannot be undone.`}
          onConfirm={remove}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
};

export default AdminBlogsPage;
