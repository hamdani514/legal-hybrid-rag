import { useLocation, useNavigate } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import OtpVerificationStep from '../components/auth/OtpVerificationStep';

const OtpVerificationPage = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // The address arrives from /forgot-password, or as a query param on a
  // resumed link.
  const searchParams = new URLSearchParams(location.search);
  const email = location.state?.email || searchParams.get('email') || '';

  return (
    <AuthShell steps={['Request code', 'Verify code', 'New password']} current={2}>
      <OtpVerificationStep
        email={email}
        onVerified={(code) => navigate('/reset-password', { state: { email, code } })}
        onChangeEmail={() => navigate('/forgot-password')}
      />
    </AuthShell>
  );
};

export default OtpVerificationPage;
