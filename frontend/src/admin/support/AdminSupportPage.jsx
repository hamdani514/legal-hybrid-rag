import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminPagination from '../components/AdminPagination';
import AdminDeleteModal from '../components/AdminDeleteModal';
import SupportQueriesTable from '../components/SupportQueriesTable';

const AdminSupportPage = () => {
  const [currentAdmin, setCurrentAdmin] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const storedAdmin = localStorage.getItem('currentAdmin');
    if (!storedAdmin) {
      navigate('/admin-login');
    } else {
      try {
        setCurrentAdmin(JSON.parse(storedAdmin));
      } catch (err) {
        console.error('Error parsing admin data:', err);
        navigate('/admin-login');
      }
    }
  }, [navigate]);

  const [queries, setQueries] = useState([]);
  const [stats, setStats] = useState({ total: 0, resolved: 0, pending: 0, urgent: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('1_to_n');
  const [currentPage, setCurrentPage] = useState(1);
  const [deleteQueryId, setDeleteQueryId] = useState(null);
  const QUERIES_PER_PAGE = 5;

  const fetchQueries = async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/admin/support');
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || 'Failed to load support queries.');
      setQueries(data.queries || []);
      setStats({
        total: data.total || 0,
        resolved: data.resolved || 0,
        pending: data.pending || 0,
        urgent: data.urgent || 0,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      if (showLoader) setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueries(true);
    const interval = setInterval(() => fetchQueries(false), 15000);
    return () => clearInterval(interval);
  }, []);

  const getStatusStyle = (status) => {
    switch (status) {
      case 'Urgent':
        return 'bg-[#FEE2E2] text-[#B91C1C] shadow-[inset_0_0_0_1px_rgba(186,26,26,0.2)]';
      case 'Pending':
        return 'bg-brand-100 text-brand-800 shadow-[inset_0_0_0_1px_rgba(0,133,255,0.28)]';
      case 'Solved':
        return 'bg-[#DCFCE7] text-[#15803D] shadow-[inset_0_0_0_1px_rgba(5,150,105,0.2)]';
      default:
        return 'bg-[#E5E7EB] text-[#111827] shadow-[inset_0_0_0_1px_rgba(117,119,126,0.2)]';
    }
  };

  const formatDateTime = (isoStr) => {
    if (!isoStr) return { date: 'N/A', time: '' };
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return { date: 'N/A', time: '' };
    const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
    return { date, time };
  };

  const getInitials = (name) => {
    if (!name) return 'AD';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  const handleStatusChange = async (queryId, newStatus) => {
    try {
      const res = await fetch(`/api/admin/support/${queryId}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.detail || 'Failed to update status.');
      }
      setQueries((prev) =>
        prev.map((q) => (q.query_id === queryId ? { ...q, status: newStatus } : q))
      );
      fetchQueries(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteQuery = async (queryId) => {
    try {
      const res = await fetch(`/api/admin/support/${queryId}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.detail || 'Failed to delete query.');
      }
      setQueries((prev) => prev.filter((q) => q.query_id !== queryId));
      fetchQueries(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleExportLogs = () => {
    if (queries.length === 0) {
      alert('No queries to export.');
      return;
    }

    const headers = ['Query ID', 'Full Name', 'Email', 'Subject', 'Message', 'Date/Time', 'Status'];
    const rows = queries.map((q) => {
      const { date, time } = formatDateTime(q.created_at);
      return [
        q.query_id || '',
        `"${(q.full_name || '').replace(/"/g, '""')}"`,
        `"${(q.email || '').replace(/"/g, '""')}"`,
        `"${(q.subject || '').replace(/"/g, '""')}"`,
        `"${(q.message || '').replace(/"/g, '""')}"`,
        `"${date} ${time}"`,
        q.status || '',
      ].join(',');
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `support_queries_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredQueries = queries.filter((q) => {
    if (statusFilter !== 'All' && q.status !== statusFilter) return false;

    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      const matchName = q.full_name?.toLowerCase().includes(term);
      const matchEmail = q.email?.toLowerCase().includes(term);
      const matchSubject = q.subject?.toLowerCase().includes(term);
      const matchId = q.query_id?.toLowerCase().includes(term);
      return matchName || matchEmail || matchSubject || matchId;
    }
    return true;
  });

  const sortedAndFilteredQueries = [...filteredQueries].sort((a, b) => {
    const numA = parseInt((a.query_id || '').replace(/\D/g, ''), 10) || 0;
    const numB = parseInt((b.query_id || '').replace(/\D/g, ''), 10) || 0;
    return sortBy === '1_to_n' ? numA - numB : numB - numA;
  });

  const totalPages = Math.ceil(sortedAndFilteredQueries.length / QUERIES_PER_PAGE);
  const safeCurrentPage = Math.min(currentPage, Math.max(totalPages, 1));
  const startIndex = (safeCurrentPage - 1) * QUERIES_PER_PAGE;
  const paginatedQueries = sortedAndFilteredQueries.slice(startIndex, startIndex + QUERIES_PER_PAGE);

  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="support" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Support & Inquiry Operations"
          subtitle="Review and manage strategic inquiries submitted through the contact channel."
          actionButtonText="Export Query Logs"
          onActionClick={handleExportLogs}
        />

        <div className="px-12 py-6 flex flex-col gap-8 flex-1">
          {error && (
            <div role="alert" className="flex items-start gap-2.5 bg-[#FEE2E2] text-[#B91C1C] p-4 rounded-lg text-xs font-prose border border-[#FEE2E2]">
              <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">
                error
              </span>
              <span>{error}</span>
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <AdminStatsCard
              label="Total Inquiries"
              value={stats.total}
              subtext="all submitted tickets"
              icon="inbox"
              loading={loading}
            />
            <AdminStatsCard
              label="Pending Review"
              value={stats.pending}
              subtext="awaiting action"
              icon="hourglass_top"
              loading={loading}
            />
            <AdminStatsCard
              label="Urgent Priority"
              value={stats.urgent}
              subtext="requires immediate focus"
              icon="priority_high"
              loading={loading}
            />
            <AdminStatsCard
              label="Solved Tickets"
              value={stats.resolved}
              subtext="successfully addressed"
              icon="check_circle"
              loading={loading}
            />
          </div>

          {/* Support Queries Table Component */}
          <div className="flex-1">
            <SupportQueriesTable
              loading={loading}
              queries={queries}
              sortedAndFilteredQueries={sortedAndFilteredQueries}
              paginatedQueries={paginatedQueries}
              statusFilter={statusFilter}
              setStatusFilter={setStatusFilter}
              searchTerm={searchTerm}
              setSearchTerm={setSearchTerm}
              sortBy={sortBy}
              setSortBy={setSortBy}
              setCurrentPage={setCurrentPage}
              handleStatusChange={handleStatusChange}
              setDeleteQueryId={setDeleteQueryId}
              getStatusStyle={getStatusStyle}
              formatDateTime={formatDateTime}
              getInitials={getInitials}
            />
            <AdminPagination
              currentPage={safeCurrentPage}
              totalPages={totalPages}
              onPageChange={setCurrentPage}
            />
          </div>
        </div>
      </main>

      {/* Delete Confirmation Modal */}
      <AdminDeleteModal
        isOpen={!!deleteQueryId}
        title="Confirm Query Deletion"
        message="Are you sure you want to delete this support inquiry? This record will be permanently purged."
        onConfirm={async () => {
          if (deleteQueryId) {
            await handleDeleteQuery(deleteQueryId);
            setDeleteQueryId(null);
          }
        }}
        onCancel={() => setDeleteQueryId(null)}
      />
    </div>
  );
};

export default AdminSupportPage;
