import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';
import HomeHero from '../components/bound/HomeHero';
import AuthorityStrip from '../components/bound/AuthorityStrip';
import JurisdictionBand from '../components/bound/JurisdictionBand';
import MethodSection from '../components/bound/MethodSection';
import ResearchFlow from '../components/bound/ResearchFlow';
import BenchQuote from '../components/bound/BenchQuote';
import CapabilityGrid from '../components/bound/CapabilityGrid';
import CorpusMosaic from '../components/bound/CorpusMosaic';
import PlansSection from '../components/bound/PlansSection';
import ClosingCTA from '../components/bound/ClosingCTA';

/**
 * Hero states the claim, the assurance strip earns the scroll, the
 * jurisdiction band shows the ground it stands on, the method explains the
 * mechanism, the two flow rows argue it, the bench quote lets the Court
 * speak, the workspace shows the tools, the mosaic shows the corpus, pricing
 * closes the argument, and the CTA offers the way in.
 *
 * The rhythm alternates deliberately: white section, tinted section,
 * full-bleed photographic band. Three photographic bands on one page is the
 * ceiling — a fourth and they stop being punctuation.
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
        <JurisdictionBand />
        <MethodSection />
        <ResearchFlow />
        <BenchQuote />
        <CapabilityGrid />
        <CorpusMosaic />
        <PlansSection />
        <ClosingCTA />
      </main>
      <SiteFoot />
    </div>
  );
};

export default HomePage;
