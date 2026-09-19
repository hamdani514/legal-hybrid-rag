import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminPagination from '../components/AdminPagination';
import AdminDeleteModal from '../components/AdminDeleteModal';
import AdminTable from '../components/AdminTable';
import AdminFormModal from '../components/AdminFormModal';

const ADMINS_PER_PAGE = 5;

const AdminManagementPage = () => {
  const [currentAdmin, setCurrentAdmin] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [stats, setStats] = useState({ total: 0, super_admins: 0, standard_admins: 0 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  const [filterQuery, setFilterQuery] = useState('');
  const [sortBy, setSortBy] = useState('id_asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [visiblePasswords, setVisiblePasswords] = useState({});

  const [modalOpen, setModalOpen] = useState(false);
  const [deleteAdminId, setDeleteAdminId] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [formData, setFormData] = useState({
    adminid: '',
    name: '',
    email: '',
    role: 'admin',
    dob: '',
    password: '',
    confirmPassword: ''
  });

  const navigate = useNavigate();

  useEffect(() => {
    const storedAdmin = localStorage.getItem('currentAdmin');
    if (!storedAdmin) {
      navigate('/admin-login');
      return;
    }

    try {
      const parsedAdmin = JSON.parse(storedAdmin);
      if (parsedAdmin.role !== 'super_admin') {
        navigate('/admin/dashboard');
        return;
      }
      setCurrentAdmin(parsedAdmin);
    } catch (err) {
      console.error('Error parsing admin data:', err);
      navigate('/admin-login');
      return;
    }

    fetchAdmins();
  }, [navigate]);

  const fetchAdmins = async () => {
    try {
      setLoading(true);
      setErrorMsg('');
      const res = await fetch('/api/admin/admins');
      if (res.ok) {
        const data = await res.json();
        setAdmins(data.admins || []);
        setStats({
          total: data.total || 0,
          super_admins: data.super_admins || 0,
          standard_admins: data.standard_admins || 0
        });
      } else {
        const data = await res.json();
        setErrorMsg(data?.detail || 'Failed to load system administrators.');
      }
    } catch (err) {
      console.error('Error fetching admins:', err);
      setErrorMsg('Failed to connect to the backend server.');
    } finally {
      setLoading(false);
    }
  };

  const getInitials = (name) => {
    if (!name) return 'A';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  const togglePasswordVisibility = (adminid) => {
    setVisiblePasswords((prev) => ({
      ...prev,
      [adminid]: !prev[adminid]
    }));
  };

  const handleAddClick = () => {
    setIsEditMode(false);
    setErrorMsg('');
    setSuccessMsg('');
    setFormData({
      adminid: '',
      name: '',
      email: '',
      role: 'admin',
      dob: '',
      password: '',
      confirmPassword: ''
    });
    setModalOpen(true);
  };

  const handleEditClick = (admin) => {
    setIsEditMode(true);
    setErrorMsg('');
    setSuccessMsg('');
    setFormData({
      adminid: admin.adminid || '',
      name: admin.name || '',
      email: admin.email || admin.adminid || '',
      role: admin.role || 'admin',
      dob: admin.dob || '',
      password: admin.password || '',
      confirmPassword: admin.password || ''
    });
    setModalOpen(true);
  };

  const handleDeleteClick = (admin) => {
    if (admin.adminid === currentAdmin?.adminid) {
      alert("You cannot delete your own logged-in administrator account.");
      return;
    }
    setDeleteAdminId(admin.adminid);
  };

  const confirmDeleteAdmin = async () => {
    if (!deleteAdminId) return;
    try {
      const res = await fetch(`/api/admin/admins/${encodeURIComponent(deleteAdminId)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchAdmins();
      } else {
        const err = await res.json();
        alert(`Error deleting admin: ${err.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting admin:', error);
      alert('Failed to connect to the backend server.');
    } finally {
      setDeleteAdminId(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!formData.name.trim()) {
      setErrorMsg('Full Name is required.');
      return;
    }

    if (!formData.adminid.trim()) {
      setErrorMsg('Admin ID is required.');
      return;
    }

    const pwRegex = /^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()_+\[\]{}|;:',.<>?/`~"\\-]).{8,}$/;
    if (!pwRegex.test(formData.password)) {
      setErrorMsg('Password must be at least 8 characters long, contain a capital letter, a small letter, a number, and a special character.');
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setErrorMsg('Password and Confirm Password do not match.');
      return;
    }

    const dobDate = new Date(formData.dob);
    if (isNaN(dobDate.getTime())) {
      setErrorMsg('Please select a valid Date of Birth.');
      return;
    }

    try {
      setSaving(true);
      const url = isEditMode ? `/api/admin/admins/${encodeURIComponent(formData.adminid)}` : '/api/admin/admins';
      const method = isEditMode ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          adminid: formData.adminid,
          name: formData.name,
          email: formData.email || formData.adminid,
          password: formData.password,
          dob: formData.dob,
          role: formData.role
        })
      });

      if (res.ok) {
        setSuccessMsg(isEditMode ? 'Admin profile updated successfully!' : 'Admin created successfully!');
        setTimeout(() => {
          setModalOpen(false);
          fetchAdmins();
        }, 1000);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'An error occurred during submission.');
      }
    } catch (error) {
      console.error('Error submitting form:', error);
      setErrorMsg('Failed to communicate with the backend server.');
    } finally {
      setSaving(false);
    }
  };

  const sortedAndFilteredAdmins = React.useMemo(() => {
    const query = filterQuery.toLowerCase().trim();
    const filtered = admins.filter((a) => {
      return (
        (a.name || '').toLowerCase().includes(query) ||
        (a.adminid || '').toLowerCase().includes(query) ||
        (a.role || '').toLowerCase().includes(query)
      );
    });

    return [...filtered].sort((a, b) => {
      if (sortBy === 'id_asc') {
        return (a.adminid || '').localeCompare(b.adminid || '');
      } else if (sortBy === 'id_desc') {
        return (b.adminid || '').localeCompare(a.adminid || '');
      } else if (sortBy === 'name_asc') {
        return (a.name || '').localeCompare(b.name || '');
      } else if (sortBy === 'name_desc') {
        return (b.name || '').localeCompare(a.name || '');
      }
      return 0;
    });
  }, [admins, filterQuery, sortBy]);

  const totalPages = Math.ceil(sortedAndFilteredAdmins.length / ADMINS_PER_PAGE);
  const safeCurrentPage = Math.min(currentPage, Math.max(totalPages, 1));
  const startIndex = (safeCurrentPage - 1) * ADMINS_PER_PAGE;
  const paginatedAdmins = sortedAndFilteredAdmins.slice(startIndex, startIndex + ADMINS_PER_PAGE);

  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="management" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Admin Management"
          subtitle="Super Administrator Suite: Overseeing administrative accounts and permissions."
          actionButtonText="Add Admin"
          onActionClick={handleAddClick}
        />

        {/* Stats Section */}
        <section className="px-12 py-6 grid grid-cols-3 gap-8">
          <AdminStatsCard
            label="Total Administrators"
            value={stats.total}
            subtext="active admin accounts"
            icon="manage_accounts"
            loading={loading}
          />
          <AdminStatsCard
            label="Super Administrators"
            value={stats.super_admins}
            subtext="full permission accounts"
            icon="shield_person"
            loading={loading}
          />
          <AdminStatsCard
            label="Standard Admins"
            value={stats.standard_admins}
            subtext="standard permission accounts"
            icon="admin_panel_settings"
            loading={loading}
          />
        </section>

        {/* Admin Table Section */}
        <section className="px-12 py-10 flex-1">
          <AdminTable
            loading={loading}
            admins={admins}
            sortedAndFilteredAdmins={sortedAndFilteredAdmins}
            paginatedAdmins={paginatedAdmins}
            filterQuery={filterQuery}
            setFilterQuery={setFilterQuery}
            sortBy={sortBy}
            setSortBy={setSortBy}
            setCurrentPage={setCurrentPage}
            visiblePasswords={visiblePasswords}
            togglePasswordVisibility={togglePasswordVisibility}
            handleEditClick={handleEditClick}
            handleDeleteClick={handleDeleteClick}
            currentAdmin={currentAdmin}
            getInitials={getInitials}
          />
          <AdminPagination
            currentPage={safeCurrentPage}
            totalPages={totalPages}
            onPageChange={setCurrentPage}
          />
        </section>
      </main>

      {/* Admin Form Modal */}
      <AdminFormModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        isEditMode={isEditMode}
        errorMsg={errorMsg}
        successMsg={successMsg}
        formData={formData}
        setFormData={setFormData}
        handleSubmit={handleSubmit}
        saving={saving}
      />

      {/* Delete Confirmation Modal */}
      <AdminDeleteModal
        isOpen={!!deleteAdminId}
        title="Confirm Administrator Deletion"
        message={`Are you sure you want to delete administrator "${deleteAdminId}"? Access for this administrator will be permanently revoked.`}
        onConfirm={confirmDeleteAdmin}
        onCancel={() => setDeleteAdminId(null)}
      />
    </div>
  );
};

export default AdminManagementPage;
