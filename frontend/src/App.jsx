import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// User Pages
import HomePage from './user/home/HomePage';
import AboutPage from './user/about/AboutPage';
import PricingPage from './user/pricing/PricingPage';
import PaymentResultPage from './user/payment/PaymentResultPage';
import ContactPage from './user/contact/ContactPage';
import FAQPage from './user/faq/FAQPage';
import BlogsPage from './user/blogs/BlogsPage';
import BlogDetailPage from './user/blogs/BlogDetailPage';
import SignupPage from './user/signup/SignupPage';
import LoginPage from './user/login/LoginPage';
import ForgotPasswordPage from './user/forgot-password/ForgotPasswordPage';
import OtpVerificationPage from './user/otp-verification/OtpVerificationPage';
import ResetPasswordPage from './user/reset-password/ResetPasswordPage';
import ReactivateAccountPage from './user/reactivate/ReactivateAccountPage';
import WelcomePage from './user/welcome/WelcomePage';
import SettingsPage from './user/account-settings/SettingsPage';
import LegalPage from './user/legal/LegalPage';
import NotFound from './user/components/bound/NotFound';

// Admin Pages
import AdminLoginPage from './admin/login/AdminLoginPage';
import AdminDashboardPage from './admin/dashboard/AdminDashboardPage';
import AdminCasesPage from './admin/cases/AdminCasesPage';
import AdminSupportPage from './admin/support/AdminSupportPage';
import AdminBlogsPage from './admin/blogs/AdminBlogsPage';
import AdminBlogEditorPage from './admin/blogs/AdminBlogEditorPage';
import AdminSettingsPage from './admin/settings/AdminSettingsPage';
import AdminManagementPage from './admin/management/AdminManagementPage';

import SessionTimeoutWatcher from './user/components/auth/SessionTimeoutWatcher';
import Toaster from './components/Toaster';
import ScrollToTop from './components/ScrollToTop';
import './App.css';

function App() {
  return (
    <Router>
      <div className="App">
        <ScrollToTop />
        <SessionTimeoutWatcher />
        <Toaster />
        <Routes>
          {/* User Routes */}
          <Route path="/" element={<HomePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/faq" element={<FAQPage />} />

          {/* Insights hub — the hub and one article per slug */}
          <Route path="/blogs" element={<BlogsPage />} />
          <Route path="/blogs/:slug" element={<BlogDetailPage />} />

          <Route path="/signup" element={<SignupPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/verify-otp" element={<OtpVerificationPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/reactivate/:token" element={<ReactivateAccountPage />} />

          {/* The research workspace: search, results, filters, summaries,
              comparison and the chat-history sidebar. /welcome is a new
              query; /chat/<slug> reopens a saved conversation (see
              src/user/lib/chatSlug.js). */}
          <Route path="/welcome" element={<WelcomePage />} />
          <Route path="/chat/:slug" element={<WelcomePage />} />
          <Route path="/chat/new" element={<Navigate to="/welcome" replace />} />
          <Route path="/chat" element={<Navigate to="/welcome" replace />} />
          <Route path="/ip_welcome" element={<Navigate to="/welcome" replace />} />

          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/account-settings" element={<SettingsPage />} />

          {/* Policy pages — LegalPage keys off the pathname slug */}
          {/* Where Stripe returns the browser after Checkout. */}
          <Route path="/payment/success" element={<PaymentResultPage />} />
          <Route path="/payment/cancel" element={<PaymentResultPage />} />

          <Route path="/privacy" element={<LegalPage />} />
          <Route path="/terms" element={<LegalPage />} />
          <Route path="/disclaimer" element={<LegalPage />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="/admin-login" element={<AdminLoginPage />} />
          <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
          <Route path="/admin/cases" element={<AdminCasesPage />} />
          <Route path="/admin/support" element={<AdminSupportPage />} />

          {/* Blog authoring — the rich-text editor lives on the two below */}
          <Route path="/admin/blogs" element={<AdminBlogsPage />} />
          <Route path="/admin/blogs/new" element={<AdminBlogEditorPage />} />
          <Route path="/admin/blogs/:slug/edit" element={<AdminBlogEditorPage />} />

          <Route path="/admin/settings" element={<AdminSettingsPage />} />
          <Route path="/admin/management" element={<AdminManagementPage />} />

          {/* Anything unmatched */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
