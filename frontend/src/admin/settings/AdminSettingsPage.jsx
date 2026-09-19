import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminSettingsForm from '../components/AdminSettingsForm';

const AdminSettingsPage = () => {
  const [currentAdmin, setCurrentAdmin] = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    adminid: '',
    name: '',
    dob: '',
    password: '',
    role: ''
  });

  useEffect(() => {
    const storedAdmin = localStorage.getItem('currentAdmin');
    if (!storedAdmin) {
      navigate('/admin-login');
      return;
    }

    let parsedAdmin;
    try {
      parsedAdmin = JSON.parse(storedAdmin);
      setCurrentAdmin(parsedAdmin);
    } catch (err) {
      console.error('Error parsing admin data:', err);
      navigate('/admin-login');
      return;
    }

    fetchProfile(parsedAdmin.adminid);
  }, [navigate]);

  const fetchProfile = async (adminid) => {
    try {
      setLoading(true);
      setErrorMsg('');
      const res = await fetch(`/api/admin/profile?adminid=${encodeURIComponent(adminid)}`);
      if (res.ok) {
        const data = await res.json();
        setFormData({
          adminid: data.adminid || '',
          name: data.name || '',
          dob: data.dob || '',
          password: data.password || '',
          role: data.role || 'admin'
        });
      } else {
        const data = await res.json();
        setErrorMsg(data?.detail || 'Failed to fetch account details.');
      }
    } catch (err) {
      console.error('Error fetching admin profile:', err);
      setErrorMsg('Failed to connect to the backend server.');
    } finally {
      setLoading(false);
    }
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!formData.name.trim()) {
      setErrorMsg('Name is required.');
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

    const dobDate = new Date(formData.dob);
    if (isNaN(dobDate.getTime())) {
      setErrorMsg('Please select a valid Date of Birth.');
      return;
    }

    try {
      setSaving(true);
      const res = await fetch('/api/admin/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          original_adminid: currentAdmin.adminid,
          adminid: formData.adminid,
          password: formData.password,
          dob: formData.dob,
          name: formData.name
        })
      });

      if (res.ok) {
        const data = await res.json();
        setSuccessMsg('Account details updated successfully!');
        
        const updatedSession = {
          adminid: data.adminid,
          name: data.name,
          role: data.role
        };
        localStorage.setItem('currentAdmin', JSON.stringify(updatedSession));
        setCurrentAdmin(updatedSession);
        
        setTimeout(() => {
          setSuccessMsg('');
        }, 3000);
      } else {
        const data = await res.json();
        setErrorMsg(data?.detail || 'An error occurred during submission.');
      }
    } catch (err) {
      console.error('Error updating profile:', err);
      setErrorMsg('Failed to communicate with the backend server.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="settings" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Account Settings"
          subtitle="Manage your administrative profile credentials and workstation security settings."
        />

        {/* Content Section */}
        <div className="px-12 py-10 flex-1 max-w-4xl">
          <AdminSettingsForm
            formData={formData}
            setFormData={setFormData}
            showPassword={showPassword}
            setShowPassword={setShowPassword}
            loading={loading}
            saving={saving}
            errorMsg={errorMsg}
            successMsg={successMsg}
            handleSubmit={handleSubmit}
            getInitials={getInitials}
          />
        </div>
      </main>
    </div>
  );
};

export default AdminSettingsPage;
