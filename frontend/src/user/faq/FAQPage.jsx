import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import PageMasthead from '../components/bound/PageMasthead';
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
        <PageMasthead
          kicker="FAQ"
          icon="quiz"
          title="The questions worth"
          accent="asking first"
          lede="What the archive holds, how retrieval actually works, where its limits are, and what happens to your research. The limits are stated as plainly as the capabilities."
          meta={[
            { label: 'Sections', value: 'Four' },
            { label: 'Questions', value: 'Ten' },
            { label: 'Reviewed', value: 'Sept 2026' },
          ]}
        />
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
