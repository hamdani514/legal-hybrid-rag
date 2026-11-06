import { lazy, Suspense, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './user/home/HomePage';
import NotFound from './user/components/bound/NotFound';
import { markPageReady } from './lib/bootSkeleton';
import SessionTimeoutWatcher from './user/components/auth/SessionTimeoutWatcher';
import Toaster from './components/Toaster';
import ScrollToTop from './components/ScrollToTop';
import './App.css';

// Pages load on demand, so a visitor downloads the code for the page they
// open rather than the whole app (the admin pages and blog editor included).
// The home page and the 404 page stay in the main bundle: the first is the
// usual landing page, the second must work even if a chunk cannot load.

// User Pages
const AboutPage = lazy(() => import('./user/about/AboutPage'));
const PricingPage = lazy(() => import('./user/pricing/PricingPage'));
const PaymentResultPage = lazy(() => import('./user/payment/PaymentResultPage'));
const ContactPage = lazy(() => import('./user/contact/ContactPage'));
const FAQPage = lazy(() => import('./user/faq/FAQPage'));
const BlogsPage = lazy(() => import('./user/blogs/BlogsPage'));
const BlogDetailPage = lazy(() => import('./user/blogs/BlogDetailPage'));
const SignupPage = lazy(() => import('./user/signup/SignupPage'));
const LoginPage = lazy(() => import('./user/login/LoginPage'));
const ForgotPasswordPage = lazy(() => import('./user/forgot-password/ForgotPasswordPage'));
const OtpVerificationPage = lazy(() => import('./user/otp-verification/OtpVerificationPage'));
const ResetPasswordPage = lazy(() => import('./user/reset-password/ResetPasswordPage'));
const ReactivateAccountPage = lazy(() => import('./user/reactivate/ReactivateAccountPage'));
const WelcomePage = lazy(() => import('./user/welcome/WelcomePage'));
const SettingsPage = lazy(() => import('./user/account-settings/SettingsPage'));
const LegalPage = lazy(() => import('./user/legal/LegalPage'));

// Admin Pages
const AdminLoginPage = lazy(() => import('./admin/login/AdminLoginPage'));
const AdminDashboardPage = lazy(() => import('./admin/dashboard/AdminDashboardPage'));
const AdminCasesPage = lazy(() => import('./admin/cases/AdminCasesPage'));
const AdminSupportPage = lazy(() => import('./admin/support/AdminSupportPage'));
const AdminBlogsPage = lazy(() => import('./admin/blogs/AdminBlogsPage'));
const AdminBlogEditorPage = lazy(() => import('./admin/blogs/AdminBlogEditorPage'));
const AdminSettingsPage = lazy(() => import('./admin/settings/AdminSettingsPage'));
const AdminManagementPage = lazy(() => import('./admin/management/AdminManagementPage'));

/** Tells the boot skeleton the routed page has drawn (see lib/bootSkeleton). */
function PageReady() {
  useEffect(() => markPageReady(), []);
  return null;
}

function App() {
  return (
    <Router>
      <div className="App">
        <ScrollToTop />
        <SessionTimeoutWatcher />
        <Toaster />
        {/* No visible fallback: on first load the boot skeleton is still up,
            and later navigations keep the current page until the next is ready. */}
        <Suspense fallback={null}>
          <PageReady />
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
        </Suspense>
      </div>
    </Router>
  );
}

export default App;
