import { Navigate, useLocation } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import LoginForm from '../components/LoginForm';
import { hasValidSession } from '../../lib/sessionManager';

// Someone already signed in never sees the login form again: any link, button
// or Back press that lands here goes on to where they were heading.
const LoginPage = () => {
  const location = useLocation();
  if (hasValidSession('user')) {
    return <Navigate to={location.state?.next || '/welcome'} replace />;
  }
  return (
    <AuthShell>
      <LoginForm />
    </AuthShell>
  );
};

export default LoginPage;
