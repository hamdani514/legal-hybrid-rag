import { Navigate } from 'react-router-dom';
import AuthShell from '../../user/components/bound/AuthShell';
import AdminLoginForm from '../components/AdminLoginForm';
import { hasValidSession } from '../../lib/sessionManager';

/**
 * Same shell and same visual panel as the researcher screens — only the
 * panel's copy switches to the admin variant, so the console reads as part of
 * one product while still being unmistakably a different door.
 *
 * An admin who is already signed in goes straight to the dashboard.
 */
const AdminLoginPage = () => {
  if (hasValidSession('admin')) {
    return <Navigate to="/admin/dashboard" replace />;
  }
  return (
    <AuthShell variant="admin">
      <AdminLoginForm />
    </AuthShell>
  );
};

export default AdminLoginPage;
