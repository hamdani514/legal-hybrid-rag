import React from 'react';
import { motion } from 'motion/react';
import { EASE_OUT_EXPO, VIEWPORT_SOFT, fadeUp, stagger } from '../motion';

const ASSURANCES = [
  { icon: 'lock', title: 'AES-256 encrypted', note: 'Every session, at rest and in transit' },
  { icon: 'visibility_off', title: 'Zero-knowledge', note: 'Your queries never train our models' },
  { icon: 'update', title: 'Indexed 4× daily', note: 'New judgments searchable within hours' },
  { icon: 'verified', title: 'Source-verified', note: 'Citations checked against the original' },
];

/**
 * The credibility beat directly under the hero. Trust-and-authority products
 * earn the scroll here, so this sits on parchment and stays deliberately
 * quiet — four assurances, one hairline, no competing call to action.
 */
const ProofBand = () => {
  return (
    <section
      aria-label="Platform assurances"
      className="relative w-full border-b border-ink-800/8 bg-parchment-100 px-5 py-14 sm:px-8 sm:py-16"
    >
      <motion.ul
        className="mx-auto grid max-w-[1280px] grid-cols-1 gap-x-8 gap-y-9 sm:grid-cols-2 lg:grid-cols-4"
        variants={stagger(0.09)}
        initial="hidden"
        whileInView="show"
        viewport={VIEWPORT_SOFT}
      >
        {ASSURANCES.map(({ icon, title, note }) => (
          <motion.li key={title} variants={fadeUp} className="group flex items-start gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-gold-500/35 bg-white text-gold-600 transition-all duration-300 group-hover:-translate-y-0.5 group-hover:border-gold-500 group-hover:shadow-gold">
              <span className="material-symbols-outlined text-lg" aria-hidden="true">
                {icon}
              </span>
            </span>
            <span className="flex flex-col">
              <span className="font-body text-sm font-bold uppercase tracking-[0.12em] text-ink-800">
                {title}
              </span>
              <motion.span
                aria-hidden="true"
                className="my-2 h-px w-8 origin-left bg-gold-500/60"
                initial={{ scaleX: 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7, ease: EASE_OUT_EXPO, delay: 0.2 }}
              />
              <span className="font-body text-sm leading-6 text-ink-600">{note}</span>
            </span>
          </motion.li>
        ))}
      </motion.ul>
    </section>
  );
};

export default ProofBand;
