import { useLocation, useNavigate } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import OtpVerificationStep from '../components/auth/OtpVerificationStep';
import { setToken } from '../../lib/api';
import { toast } from '../../lib/toast';

const OtpVerificationPage = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // The address arrives from /forgot-password, /signup, or query param
  const searchParams = new URLSearchParams(location.search);
  const email = location.state?.email || searchParams.get('email') || '';
  const flow = location.state?.flow || searchParams.get('flow') || 'reset';
  const isSignup = flow === 'signup';

  const handleVerified = (code, authData) => {
    if (isSignup) {
      if (authData?.token) {
        setToken(authData.token);
        localStorage.setItem('currentUser', JSON.stringify(authData.user));
        toast.success('Account created successfully. Welcome to Verdict AI!');
        navigate('/welcome');
      } else {
        toast.success('Account created successfully. Please sign in.');
        navigate('/login');
      }
    } else {
      navigate('/reset-password', { state: { email, code } });
    }
  };

  const handleChangeEmail = () => {
    if (isSignup) {
      navigate('/signup');
    } else {
      navigate('/forgot-password');
    }
  };

  const steps = isSignup
    ? ['Account details', 'Verify email', 'Workspace ready']
    : ['Request code', 'Verify code', 'New password'];

  return (
    <AuthShell steps={steps} current={2}>
      <OtpVerificationStep
        email={email}
        flow={flow}
        onVerified={handleVerified}
        onChangeEmail={handleChangeEmail}
      />
    </AuthShell>
  );
};

export default OtpVerificationPage;

