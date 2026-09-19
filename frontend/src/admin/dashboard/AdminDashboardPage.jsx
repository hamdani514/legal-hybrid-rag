import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminPagination from '../components/AdminPagination';
import AdminDeleteModal from '../components/AdminDeleteModal';
import UserTable from '../components/UserTable';
import UserFormModal from '../components/UserFormModal';

const USERS_PER_PAGE = 10;

const AdminDashboardPage = () => {
  const [users, setUsers] = useState([]);
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

  const [stats, setStats] = useState({ total_users: 0, pro_users: 0, standard_users: 0 });
  const [loading, setLoading] = useState(true);
  const [filterQuery, setFilterQuery] = useState('');
  const [sortBy, setSortBy] = useState('id_asc');
  const [currentPage, setCurrentPage] = useState(1);

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteUserId, setDeleteUserId] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [formData, setFormData] = useState({
    id: '',
    username: '',
    name: '',
    email: '',
    org: '',
    plan: 'Standard',
    password: '',
    dob: '',
    gender: 'Male',
    phone_no: ''
  });

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/admin/users');
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users || []);
        setStats({
          total_users: data.total_users || 0,
          pro_users: data.pro_users || 0,
          standard_users: data.standard_users || 0
        });
      }
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddClick = () => {
    setIsEditMode(false);
    setErrorMsg('');
    setSuccessMsg('');
    setFormData({
      id: '',
      username: '',
      name: '',
      email: '',
      org: '',
      plan: 'Standard',
      password: '',
      dob: '',
      gender: 'Male',
      phone_no: ''
    });
    setModalOpen(true);
  };

  const handleEditClick = (user) => {
    setIsEditMode(true);
    setErrorMsg('');
    setSuccessMsg('');
    setFormData({
      id: user.id || '',
      username: user.username || '',
      name: user.name || '',
      email: user.email || '',
      org: user.org || '',
      plan: user.plan || 'Standard',
      password: user.password || '',
      dob: user.dob || '',
      gender: user.gender || 'Male',
      phone_no: user.phone_no || ''
    });
    setModalOpen(true);
  };

  const handleDeleteClick = (user) => {
    setDeleteUserId(user.id);
  };

  const confirmDeleteUser = async () => {
    if (!deleteUserId) return;
    try {
      const res = await fetch(`/api/admin/users/${deleteUserId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchUsers();
      } else {
        const err = await res.json();
        alert(`Error deleting user: ${err.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting user:', error);
      alert('Failed to connect to the backend server.');
    } finally {
      setDeleteUserId(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!formData.email.toLowerCase().endsWith('@gmail.com')) {
      setErrorMsg('Email must contain @gmail.com domain.');
      return;
    }

    const pwRegex = /^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()_+\[\]{}|;:',.<>?/`~"\\-]).{8,}$/;
    if (!pwRegex.test(formData.password)) {
      setErrorMsg('Password must be at least 8 characters long, contain a capital letter, a small letter, a number, and a special character.');
      return;
    }

    const dobDate = new Date(formData.dob);
    if (isNaN(dobDate.getTime())) {
      setErrorMsg('Please select a valid Date of Birth.');
      return;
    }

    const originalUser = isEditMode ? users.find(u => u.id === formData.id) : null;
    const regDateStr = originalUser?.created_at || new Date().toISOString();
    const regDate = new Date(regDateStr);

    let age = regDate.getFullYear() - dobDate.getFullYear();
    const monthDiff = regDate.getMonth() - dobDate.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && regDate.getDate() < dobDate.getDate())) {
      age--;
    }

    if (age < 16) {
      setErrorMsg('User must be older than 16 years from the registration date.');
      return;
    }

    try {
      const url = isEditMode ? `/api/admin/users/${formData.id}` : '/api/admin/users';
      const method = isEditMode ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (res.ok) {
        setSuccessMsg(isEditMode ? 'User profile updated successfully!' : 'User created successfully!');
        setTimeout(() => {
          setModalOpen(false);
          fetchUsers();
        }, 1000);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'An error occurred during submission.');
      }
    } catch (error) {
      console.error('Error submitting form:', error);
      setErrorMsg('Failed to communicate with the backend server.');
    }
  };

  const handlePlanChange = async (userId, newPlan) => {
    try {
      const res = await fetch(`/api/admin/users/${userId}/plan`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ plan: newPlan })
      });
      if (res.ok) {
        setUsers(users.map(u => u.id === userId ? { ...u, plan: newPlan } : u));
        fetchUsers();
      } else {
        const err = await res.json();
        alert(`Error updating plan: ${err.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error updating plan:', error);
      alert('Failed to connect to the backend server.');
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
          actionButtonText="Add User"
          onActionClick={handleAddClick}
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
            label="Total Pro Plan"
            value={stats.pro_users}
            subtext="active pro subscribers"
            icon="workspace_premium"
            loading={loading}
          />
          <AdminStatsCard
            label="Total Standard Plan"
            value={stats.standard_users}
            subtext="active basic plan users"
            icon="grade"
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
            handlePlanChange={handlePlanChange}
            handleEditClick={handleEditClick}
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

      {/* User Form Modal */}
      <UserFormModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        isEditMode={isEditMode}
        errorMsg={errorMsg}
        successMsg={successMsg}
        formData={formData}
        setFormData={setFormData}
        handleSubmit={handleSubmit}
      />

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
