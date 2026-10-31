import { Navigate } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import SignupForm from '../components/SignupForm';
import { hasValidSession } from '../../lib/sessionManager';

// A signed-in user who follows a "Create account" link goes to the research
// workspace instead of the signup form.
const SignupPage = () => {
  if (hasValidSession('user')) {
    return <Navigate to="/welcome" replace />;
  }
  return (
    <AuthShell>
      <SignupForm />
    </AuthShell>
  );
};

export default SignupPage;
