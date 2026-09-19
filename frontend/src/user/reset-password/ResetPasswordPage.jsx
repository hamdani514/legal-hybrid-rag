import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import AuthShell from '../components/bound/AuthShell';
import ResetPasswordStep from '../components/auth/ResetPasswordStep';
import AuthSuccessStep from '../components/auth/AuthSuccessStep';

const ResetPasswordPage = () => {
  const [isSuccess, setIsSuccess] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const searchParams = new URLSearchParams(location.search);
  const email = location.state?.email || searchParams.get('email') || '';

  return (
    <AuthShell steps={['Request code', 'Verify code', 'New password']} current={3}>
      {isSuccess ? (
        <AuthSuccessStep email={email} onDone={() => navigate('/login')} />
      ) : (
        <ResetPasswordStep email={email} onPasswordReset={() => setIsSuccess(true)} />
      )}
    </AuthShell>
  );
};

export default ResetPasswordPage;
