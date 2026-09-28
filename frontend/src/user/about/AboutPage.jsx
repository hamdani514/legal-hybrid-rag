import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import DivisionsTicker from '../components/bound/DivisionsTicker';
import OriginSection from '../components/bound/OriginSection';
import PrincipleList from '../components/bound/PrincipleList';
import MetricsBand from '../components/bound/MetricsBand';
import ClosingCTA from '../components/bound/ClosingCTA';

const AboutPage = () => {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />
      <main id="main-content" className="w-full flex-1">
        <HomeHero
          badge="Architectural Blueprint · How Retrieval Works"
          title="Research that starts where the"
          accent="judicial reasoning is"
          description="Most search engines look for keywords. We divide every reported Supreme Court judgment into its six core parts so your query reaches the exact passage that decides the law — not just the text that mentions it."
          primaryCta={{ to: '/signup', label: 'Start researching free', icon: 'arrow_forward' }}
          secondaryCta={{ to: '/faq', label: 'Read common questions', icon: 'help' }}
          highlights={[
            { icon: 'account_tree', label: 'Six divisions marked' },
            { icon: 'travel_explore', label: 'Two-stage semantic retrieval' },
            { icon: 'verified', label: 'Direct authority citations' },
          ]}
        />
        <DivisionsTicker />
        <OriginSection />
        <PrincipleList />
        <MetricsBand />
        <ClosingCTA
          eyebrow="Try it"
          title="Read the method, then"
          accent="put it to a question."
          lede="The fastest way to judge a research tool is to ask it something you already know the answer to."
          primary={{ to: '/signup', label: 'Create free account' }}
          secondary={{ to: '/faq', label: 'Read the FAQ' }}
        />
      </main>
      <SiteFoot />
    </div>
  );
};

export default AboutPage;
