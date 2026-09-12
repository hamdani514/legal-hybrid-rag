import React from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import CinematicHeading, { Eyebrow } from './cinematic/CinematicHeading';
import { AuraField, ColonnadeLayer, LightSweep, Vignette } from './cinematic/Atmosphere';

/**
 * The banner every user-facing page opens with.
 *
 * A parchment ground, a pale stone colonnade anchoring the base, and a warm
 * aura for depth. Texture is deliberately kept out from under the copy — the
 * artwork is held to the outer thirds and the middle stays clean so the
 * headline and standfirst read at full contrast.
 */

const ART = {
  chamber: { src: '/assets/legal/chamber.svg', alt: 'Supreme court chamber interior' },
  library: { src: '/assets/legal/archive-library.svg', alt: 'Law library of bound judgment volumes' },
  none: null,
};

// Top padding clears the fixed masthead (84px at rest), so a page can start
// with the banner and still sit flush against the viewport.
const SIZES = {
  sm: 'min-h-[38vh] pb-14 pt-32 sm:pb-16 sm:pt-36',
  md: 'min-h-[48vh] pb-16 pt-32 sm:pb-20 sm:pt-40',
  lg: 'min-h-[58vh] pb-20 pt-36 sm:pb-24 sm:pt-44 lg:pt-48',
};

const PageBanner = ({
  eyebrow,
  title,
  subtitle,
  art = 'chamber',
  size = 'md',
  breadcrumb = [],
  meta = [],
  children,
  className = '',
}) => {
  const ref = React.useRef(null);
  const shouldReduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });

  const artY = useTransform(scrollYProgress, [0, 1], ['0%', '14%']);
  const copyY = useTransform(scrollYProgress, [0, 1], [0, -40]);

  const artwork = ART[art];

  // First line stays ink, the remainder runs in gold — a full-gold heading
  // reads as decoration rather than as the page title.
  const firstLineWords = String(title).split('|')[0].trim().split(/\s+/).length;

  return (
    <section
      ref={ref}
      className={`relative isolate w-full overflow-hidden surface-parchment ${SIZES[size]} ${className}`}
    >
      {/* Artwork, held to the right so it never sits behind the copy */}
      {artwork && (
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 hidden w-[42%] lg:block"
          style={shouldReduce ? undefined : { y: artY }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.55 }}
          transition={{ duration: 1.2 }}
        >
          <img src={artwork.src} alt="" loading="eager" className="h-full w-full object-cover" />
          {/* Feathered edge so the plate dissolves into the page */}
          <span
            className="absolute inset-0"
            style={{
              background:
                'linear-gradient(90deg, #FAF7F0 0%, rgba(250,247,240,0.9) 26%, rgba(250,247,240,0.35) 65%, rgba(250,247,240,0.25) 100%)',
            }}
          />
        </motion.div>
      )}

      <AuraField />
      <LightSweep duration={14} />
      <ColonnadeLayer opacity={0.35} distance={30} className="h-[36%]" />
      <Vignette strength={0.3} />

      {/* Copy */}
      <motion.div
        className="relative z-10 mx-auto w-full max-w-[1280px] px-5 sm:px-8"
        style={shouldReduce ? undefined : { y: copyY }}
      >
        {breadcrumb.length > 0 && (
          <motion.nav
            aria-label="Breadcrumb"
            className="mb-6 flex flex-wrap items-center gap-2 font-body text-xs text-ink-500"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            {breadcrumb.map((crumb, i) => (
              <React.Fragment key={crumb.label}>
                {i > 0 && (
                  <span aria-hidden="true" className="text-ink-300">
                    /
                  </span>
                )}
                {crumb.to ? (
                  <Link to={crumb.to} className="link-wipe transition-colors hover:text-gold-700">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="font-semibold text-ink-700">
                    {crumb.label}
                  </span>
                )}
              </React.Fragment>
            ))}
          </motion.nav>
        )}

        {eyebrow && <Eyebrow delay={0.1}>{eyebrow}</Eyebrow>}

        <CinematicHeading
          as="h1"
          text={title}
          delay={0.25}
          accentFrom={firstLineWords}
          className="mt-6 max-w-[16ch] font-headline text-[clamp(2.4rem,6.4vw,4.5rem)] font-normal leading-[1.05] tracking-[-0.04em] text-ink-900"
        />

        {subtitle && (
          <motion.p
            className="mt-6 max-w-[56ch] font-body text-base leading-8 text-ink-600 sm:text-lg"
            initial={{ opacity: 0, y: shouldReduce ? 0 : 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.65 }}
          >
            {subtitle}
          </motion.p>
        )}

        {children && (
          <motion.div
            className="mt-9 flex flex-wrap items-center gap-4"
            initial={{ opacity: 0, y: shouldReduce ? 0 : 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.8 }}
          >
            {children}
          </motion.div>
        )}

        {meta.length > 0 && (
          <motion.dl
            className="mt-12 grid max-w-3xl grid-cols-1 gap-px overflow-hidden rounded-lg border border-ink-800/10 bg-ink-800/10 sm:grid-cols-3"
            initial={{ opacity: 0, y: shouldReduce ? 0 : 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.95 }}
          >
            {meta.map(({ label, value }) => (
              <div key={label} className="bg-white px-5 py-4">
                <dt className="font-body text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-500">
                  {label}
                </dt>
                <dd className="mt-1.5 font-headline text-lg text-ink-800 sm:text-xl">{value}</dd>
              </div>
            ))}
          </motion.dl>
        )}
      </motion.div>

      {/* Base hairline — the seam between banner and page */}
      <div aria-hidden="true" className="absolute inset-x-0 bottom-0 z-10 h-px rule-gold" />
    </section>
  );
};

export default PageBanner;
