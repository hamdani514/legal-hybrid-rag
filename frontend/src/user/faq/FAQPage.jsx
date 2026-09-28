import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import DivisionsTicker from '../components/bound/DivisionsTicker';
import FaqGroups from '../components/bound/FaqGroups';
import ClosingCTA from '../components/bound/ClosingCTA';

const FAQPage = () => {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />
      <main id="main-content" className="w-full flex-1">
        <HomeHero
          badge="Knowledge Base · Archive & Method Answers"
          title="Clear answers to how our"
          accent="archive & engine work"
          description="Curious about corpus coverage, privacy guarantees, citations, or retrieval accuracy? Here is everything you need to know about the platform before stepping into the research suite."
          primaryCta={{ to: '/signup', label: 'Create free account', icon: 'arrow_forward' }}
          secondaryCta={{ to: '/contact', label: 'Ask a specific question', icon: 'mail' }}
          highlights={[
            { icon: 'menu_book', label: '10 core topics covered' },
            { icon: 'lock', label: 'Encrypted research queries' },
            { icon: 'rule', label: 'Plain limits stated' },
          ]}
        />
        <DivisionsTicker />
        <FaqGroups />
        <ClosingCTA
          eyebrow="Still unanswered"
          title="Ask the question the"
          accent="FAQ missed."
          lede="If it concerns a particular judgment, send the appeal number and the passage with it."
          primary={{ to: '/contact', label: 'Write to us' }}
          secondary={{ to: '/about', label: 'How it works' }}
        />
      </main>
      <SiteFoot />
    </div>
  );
};

export default FAQPage;
