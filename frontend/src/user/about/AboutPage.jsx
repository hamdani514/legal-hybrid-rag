import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import PageMasthead from '../components/bound/PageMasthead';
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
        <PageMasthead
          kicker="How it works"
          icon="route"
          title="Research that starts where the"
          accent="reasoning is"
          lede="Every reported judgment is divided into its working parts before a single query runs, so a match returns the passage that decides the point — not the document that mentions it."
          meta={[
            { label: 'Jurisdiction', value: 'Supreme Court of Pakistan' },
            { label: 'Divisions', value: 'Six per judgment' },
            { label: 'Retrieval', value: 'Two-stage semantic' },
          ]}
          media="court"
          mediaCaption="Supreme Court of Pakistan · Islamabad"
        />
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
