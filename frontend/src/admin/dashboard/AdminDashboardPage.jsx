import { useCallback, useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminPagination from '../components/AdminPagination';
import AdminDeleteModal from '../components/AdminDeleteModal';
import UserTable from '../components/UserTable';
import { apiFetch } from '../../lib/api';
import useToastOn from '../../lib/useToastOn';
import { readStoredAdmin } from '../session';

const USERS_PER_PAGE = 10;

/** Every user with the plan counts, or null if the list could not be loaded. */
const requestUsers = async () => {
  try {
    const res = await apiFetch('/api/admin/users');
    return res.ok ? await res.json() : null;
  } catch (error) {
    console.error('Error fetching users:', error);
    return null;
  }
};

const AdminDashboardPage = () => {
  const [users, setUsers] = useState([]);
  const [currentAdmin] = useState(readStoredAdmin);
  const navigate = useNavigate();

  useEffect(() => {
    if (!currentAdmin) navigate('/admin-login');
  }, [currentAdmin, navigate]);

  const [stats, setStats] = useState({ total_users: 0, premium_users: 0, standard_users: 0 });
  const [loading, setLoading] = useState(true);
  const [filterQuery, setFilterQuery] = useState('');
  const [sortBy, setSortBy] = useState('id_asc');
  const [currentPage, setCurrentPage] = useState(1);

  // Admins can view and delete users, never edit them (see UserTable).
  const [deleteUserId, setDeleteUserId] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  useToastOn(errorMsg, 'error');
  useToastOn(successMsg, 'success');

  // `loading` starts true for the first load; a refresh after a delete updates
  // the table in place rather than flashing the loader again.
  const showUsers = useCallback((data) => {
    if (data) {
      setUsers(data.users || []);
      setStats({
        total_users: data.total_users || 0,
        premium_users: data.premium_users || 0,
        standard_users: data.standard_users || 0,
      });
    }
    setLoading(false);
  }, []);
  const fetchUsers = () => requestUsers().then(showUsers);

  useEffect(() => {
    requestUsers().then(showUsers);
  }, [showUsers]);

  const handleDeleteClick = (user) => {
    setDeleteUserId(user.id);
  };

  const confirmDeleteUser = async () => {
    if (!deleteUserId) return;
    try {
      const res = await apiFetch(`/api/admin/users/${deleteUserId}`, {
        method: 'DELETE'
      });
      setErrorMsg('');
      setSuccessMsg('');
      if (res.ok) {
        setSuccessMsg('User deleted successfully.');
        fetchUsers();
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMsg(`Error deleting user: ${err.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting user:', error);
      setErrorMsg('Failed to connect to the backend server.');
    } finally {
      setDeleteUserId(null);
    }
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  const sortedAndFilteredUsers = useMemo(() => {
    const query = filterQuery.toLowerCase().trim();
    const filtered = users.filter((u) => {
      return (
        (u.name || '').toLowerCase().includes(query) ||
        (u.email || '').toLowerCase().includes(query) ||
        (u.username || '').toLowerCase().includes(query) ||
        (u.org || '').toLowerCase().includes(query) ||
        (u.phone_no || '').toLowerCase().includes(query) ||
        (u.id || '').toLowerCase().includes(query)
      );
    });

    return [...filtered].sort((a, b) => {
      if (sortBy === 'id_asc') {
        return (a.id || '').localeCompare(b.id || '', undefined, { numeric: true, sensitivity: 'base' });
      } else if (sortBy === 'id_desc') {
        return (b.id || '').localeCompare(a.id || '', undefined, { numeric: true, sensitivity: 'base' });
      } else if (sortBy === 'name_asc') {
        return (a.name || '').localeCompare(b.name || '');
      } else if (sortBy === 'name_desc') {
        return (b.name || '').localeCompare(a.name || '');
      }
      return 0;
    });
  }, [users, filterQuery, sortBy]);

  const totalPages = Math.ceil(sortedAndFilteredUsers.length / USERS_PER_PAGE);
  const safeCurrentPage = Math.min(currentPage, Math.max(totalPages, 1));
  const startIndex = (safeCurrentPage - 1) * USERS_PER_PAGE;
  const paginatedUsers = sortedAndFilteredUsers.slice(startIndex, startIndex + USERS_PER_PAGE);

  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="dashboard" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Management Suite"
          subtitle="Orchestrating professional identities and permissions."
        />

        {/* Stats Section */}
        <section className="px-12 py-6 grid grid-cols-3 gap-8">
          <AdminStatsCard
            label="Total User"
            value={stats.total_users}
            subtext="registered accounts"
            icon="group"
            loading={loading}
          />
          <AdminStatsCard
            label="Total Standard Plan"
            value={stats.standard_users}
            subtext="$10 / month subscribers"
            icon="grade"
            loading={loading}
          />
          <AdminStatsCard
            label="Total Premium Plan"
            value={stats.premium_users}
            subtext="$20 / month subscribers"
            icon="workspace_premium"
            loading={loading}
          />
        </section>

        {/* User Table Section */}
        <section className="px-12 py-10 flex-1">
          <UserTable
            loading={loading}
            users={users}
            sortedAndFilteredUsers={sortedAndFilteredUsers}
            paginatedUsers={paginatedUsers}
            filterQuery={filterQuery}
            setFilterQuery={setFilterQuery}
            sortBy={sortBy}
            setSortBy={setSortBy}
            setCurrentPage={setCurrentPage}
            handleDeleteClick={handleDeleteClick}
            getInitials={getInitials}
          />
          <AdminPagination
            currentPage={safeCurrentPage}
            totalPages={totalPages}
            onPageChange={setCurrentPage}
          />
        </section>
      </main>

      {/* Delete Confirmation Modal */}
      <AdminDeleteModal
        isOpen={!!deleteUserId}
        title="Confirm User Deletion"
        message="Are you sure you want to delete this user? All user data will be permanently removed."
        onConfirm={confirmDeleteUser}
        onCancel={() => setDeleteUserId(null)}
      />
    </div>
  );
};

export default AdminDashboardPage;
