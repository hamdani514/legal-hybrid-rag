import AuthShell from '../../user/components/bound/AuthShell';
import AdminLoginForm from '../components/AdminLoginForm';

/**
 * Same shell and same visual panel as the researcher screens — only the
 * panel's copy switches to the admin variant, so the console reads as part of
 * one product while still being unmistakably a different door.
 */
const AdminLoginPage = () => (
  <AuthShell variant="admin">
    <AdminLoginForm />
  </AuthShell>
);

export default AdminLoginPage;
