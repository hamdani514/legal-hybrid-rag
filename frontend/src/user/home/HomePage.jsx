import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import AuthorityStrip from '../components/bound/AuthorityStrip';
import MethodSection from '../components/bound/MethodSection';
import CapabilityGrid from '../components/bound/CapabilityGrid';
import PlansSection from '../components/bound/PlansSection';
import ClosingCTA from '../components/bound/ClosingCTA';

/**
 * Hero states the claim, the assurance strip earns the scroll, the method
 * explains the mechanism, the workspace shows the tools, pricing closes the
 * argument, and the CTA offers the way in.
 */
const HomePage = () => {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />
      <main id="main-content" className="w-full flex-1">
        <HomeHero />
        <AuthorityStrip />
        <MethodSection />
        <CapabilityGrid />
        <PlansSection />
        <ClosingCTA />
      </main>
      <SiteFoot />
    </div>
  );
};

export default HomePage;
