import React, { useRef } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import { LightSweep, Vignette } from './cinematic/Atmosphere';
import { ScalesMark } from './cinematic/LegalMark';
import ActionLink from './ui/ActionLink';
import { EASE_OUT_EXPO, VIEWPORT_SOFT } from '../motion';

/**
 * The mid-page interlude — a full-bleed linen band that breaks the page in
 * two. The chamber plate is parallaxed and heavily washed out, so the band
 * reads as a held shot without ever competing with the quotation.
 */
const InterludeBanner = () => {
  const ref = useRef(null);
  const shouldReduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });

  const artY = useTransform(scrollYProgress, [0, 1], ['-14%', '14%']);
  const artScale = useTransform(scrollYProgress, [0, 0.5, 1], [1.12, 1.02, 1.12]);

  return (
    <section
      ref={ref}
      aria-labelledby="interlude-heading"
      className="relative isolate w-full overflow-hidden surface-linen"
    >
      {/* Artwork */}
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={shouldReduce ? undefined : { y: artY, scale: artScale }}
      >
        <img
          src="/assets/legal/chamber.svg"
          alt=""
          loading="lazy"
          className="h-full w-full object-cover opacity-70"
        />
      </motion.div>

      {/* Wash the plate back so the quotation sits on near-flat linen */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(70% 60% at 50% 50%, rgba(246,241,228,0.95) 0%, rgba(243,237,221,0.85) 45%, rgba(233,224,204,0.7) 100%)',
        }}
      />
      <LightSweep duration={16} />
      <Vignette strength={0.28} />

      <div className="relative z-10 mx-auto flex max-w-[1000px] flex-col items-center px-5 py-28 text-center sm:px-8 sm:py-36 lg:py-44">
        <motion.div
          initial={{ opacity: 0, scale: shouldReduce ? 1 : 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={VIEWPORT_SOFT}
          transition={{ duration: 1, ease: EASE_OUT_EXPO }}
        >
          <ScalesMark className="text-gold-700" size={64} />
        </motion.div>

        <motion.blockquote
          id="interlude-heading"
          className="mt-10 font-headline text-[clamp(1.6rem,4.2vw,2.9rem)] font-normal leading-[1.28] tracking-[-0.03em] text-ink-900"
          initial={{ opacity: 0, y: shouldReduce ? 0 : 26 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT_SOFT}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.15 }}
        >
          <span aria-hidden="true" className="text-gold-600">
            “
          </span>
          Precedent is not a filing cabinet. It is an argument waiting to be{' '}
          <span className="text-gradient-gold text-gradient-gold--animated">found</span>.
          <span aria-hidden="true" className="text-gold-600">
            ”
          </span>
        </motion.blockquote>

        <motion.p
          className="mt-8 max-w-[56ch] font-body text-base leading-7 text-ink-600"
          initial={{ opacity: 0, y: shouldReduce ? 0 : 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT_SOFT}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO, delay: 0.3 }}
        >
          Verdict AI reads the full text of every Supreme Court judgment in the archive, then ranks what
          actually bears on the matter in front of you — with the passage and the page it came from.
        </motion.p>

        <motion.div
          className="mt-11 flex flex-wrap items-center justify-center gap-4"
          initial={{ opacity: 0, y: shouldReduce ? 0 : 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT_SOFT}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO, delay: 0.42 }}
        >
          <ActionLink to="/welcome" variant="ink" size="lg">
            Open the research console
          </ActionLink>
          <ActionLink to="/about" variant="outline" size="lg" icon="north_east">
            How it works
          </ActionLink>
        </motion.div>
      </div>

      <span aria-hidden="true" className="absolute inset-x-0 top-0 z-10 h-px rule-gold" />
      <span aria-hidden="true" className="absolute inset-x-0 bottom-0 z-10 h-px rule-gold" />
    </section>
  );
};

export default InterludeBanner;
