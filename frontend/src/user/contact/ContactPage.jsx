import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import PageMasthead from '../components/bound/PageMasthead';
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
        <PageMasthead
          kicker="Contact"
          icon="mail"
          title="We usually reply"
          accent="within a day"
          lede="Student verification, chambers access, or a citation that came back wrong — it reaches a person either way."
          meta={[
            { label: 'Enquiries', value: 'One working day' },
            { label: 'Retrieval faults', value: 'Same-day triage' },
            { label: 'Based in', value: 'Islamabad' },
          ]}
        />
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
