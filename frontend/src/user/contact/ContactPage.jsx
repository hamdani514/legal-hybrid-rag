import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import DivisionsTicker from '../components/bound/DivisionsTicker';
import ContactPanel from '../components/bound/ContactPanel';
import ClosingCTA from '../components/bound/ClosingCTA';

const ContactPage = () => {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />
      <main id="main-content" className="w-full flex-1">
        <HomeHero
          badge="Chamber Support & Inquiries · Islamabad Desk"
          title="Direct legal research assistance"
          accent="when you need it"
          description="Need help verifying an academic email, setting up multi-lawyer chamber billing, or requesting specific case coverage? Our legal engineering desk is here to help."
          primaryCta={{ to: '/signup', label: 'Start researching free', icon: 'arrow_forward' }}
          secondaryCta={{ to: '/faq', label: 'Explore the FAQ', icon: 'help' }}
          highlights={[
            { icon: 'support_agent', label: 'Same-day triage' },
            { icon: 'apartment', label: 'Chambers onboarding' },
            { icon: 'location_on', label: 'Islamabad research desk' },
          ]}
        />
        <DivisionsTicker />
        <ContactPanel />
        <ClosingCTA
          eyebrow="Meanwhile"
          title="You do not have to"
          accent="wait to start."
          lede="Student access is free on an institutional address, and the archive opens the moment your account is confirmed."
          primary={{ to: '/signup', label: 'Create free account' }}
          secondary={{ to: '/faq', label: 'Read the FAQ' }}
        />
      </main>
      <SiteFoot />
    </div>
  );
};

export default ContactPage;
