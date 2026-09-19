import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import ForgotPasswordStep from '../components/auth/ForgotPasswordStep';

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const navigate = useNavigate();

  // Carry the address forward so the OTP screen can address it by name.
  const handleOtpSent = (submittedEmail) => {
    navigate('/verify-otp', { state: { email: submittedEmail } });
  };

  return (
    <AuthShell steps={['Request code', 'Verify code', 'New password']} current={1}>
      <ForgotPasswordStep
        email={email}
        setEmail={setEmail}
        onOtpSent={handleOtpSent}
        onBackToLogin={() => navigate('/login')}
      />
    </AuthShell>
  );
};

export default ForgotPasswordPage;
