import React from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { Eyebrow } from './cinematic/CinematicHeading';
import { AuraField, ColonnadeLayer, LightSweep, Vignette } from './cinematic/Atmosphere';
import { ScalesMark, SealMark } from './cinematic/LegalMark';
import { EASE_OUT_EXPO } from '../motion';

/**
 * Shared cinematic shell for /login and /signup.
 *
 * A linen stage on one side carries the artwork and the promise; the form
 * sits on parchment on the other. On small screens the stage collapses to a
 * compact banner above the form so the page still opens with the brand.
 */
const AuthLayout = ({
  eyebrow,
  title,
  blurb,
  bullets = [],
  footnote,
  children,
  reverse = false,
}) => {
  const shouldReduce = useReducedMotion();

  // Both halves are light, so the masthead uses one set of ink chrome
  // regardless of which side the stage is on.
  const brandTone = 'text-ink-900';
  const helpTone = 'text-ink-600 hover:text-ink-900';
  const backTone = 'border-ink-800/25 text-ink-700 hover:border-gold-600 hover:bg-gold-50';

  return (
    <div className="flex min-h-screen w-full flex-col bg-parchment-50">
      {/* Minimal masthead */}
      <header className="absolute inset-x-0 top-0 z-30 flex h-20 items-center justify-between px-5 sm:px-8">
        <Link to="/" className="group flex items-center gap-3" aria-label="Verdict AI, home">
          <span className="relative flex h-9 w-9 items-center justify-center">
            <span
              aria-hidden="true"
              className="absolute inset-0 rounded-full border border-gold-600/50 transition-transform duration-500 group-hover:rotate-90"
            />
            <svg viewBox="0 0 200 200" className="h-5 w-5 text-gold-700" fill="none" aria-hidden="true">
              <g stroke="currentColor" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round">
                <path d="M100 40v120M40 66h120M60 178h80" />
                <path d="M40 66 18 118h44zM160 66l22 52h-44z" />
              </g>
            </svg>
          </span>
          <span className={`font-headline text-xl font-bold tracking-[-0.03em] sm:text-2xl ${brandTone}`}>
            Verdict AI
          </span>
        </Link>

        <div className="flex items-center gap-5">
          <Link
            to="/faq"
            className={`link-wipe hidden font-body text-sm transition-colors sm:inline-block ${helpTone}`}
          >
            Help
          </Link>
          <Link
            to="/"
            className={`rounded-lg border px-4 py-2 font-body text-[11px] font-bold uppercase tracking-[0.16em] backdrop-blur-sm transition-colors duration-300 ${backTone}`}
          >
            Back home
          </Link>
        </div>
      </header>

      <main
        id="main-content"
        className={`flex min-h-screen flex-1 flex-col ${reverse ? 'lg:flex-row-reverse' : 'lg:flex-row'}`}
      >
        {/* Ink stage — carries the page h1, so it is real content */}
        <section
          aria-labelledby="auth-stage-heading"
          className="relative isolate flex min-h-[42vh] flex-col justify-end overflow-hidden border-ink-800/10 surface-linen px-6 pb-12 pt-28 sm:px-12 lg:min-h-screen lg:w-1/2 lg:border-r lg:pb-20 lg:pt-32"
        >
          <motion.div
            className="pointer-events-none absolute inset-0"
            initial={{ opacity: 0, scale: shouldReduce ? 1 : 1.1 }}
            animate={{ opacity: 0.9, scale: 1 }}
            transition={{ duration: 1.6, ease: EASE_OUT_EXPO }}
          >
            <img
              src="/assets/legal/chamber.svg"
              alt=""
              className="h-full w-full object-cover"
              loading="eager"
            />
          </motion.div>

          {/* Wash the plate back — the promise copy sits directly over it */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                'linear-gradient(0deg, #F6F1E4 6%, rgba(246,241,228,0.92) 40%, rgba(246,241,228,0.62) 100%)',
            }}
          />
          <AuraField />
          <LightSweep duration={14} />
          <ColonnadeLayer opacity={0.45} distance={28} className="h-[45%]" />
          <Vignette strength={0.25} />

          <SealMark className="absolute right-8 top-28 text-gold-600/12 lg:top-40" size={220} />

          <div className="relative z-10 max-w-[34rem]">
            <ScalesMark className="mb-8 text-gold-700" size={54} />

            {eyebrow && <Eyebrow delay={0.15}>{eyebrow}</Eyebrow>}

            <motion.h1
              id="auth-stage-heading"
              className="mt-6 font-headline text-[clamp(2rem,4.6vw,3.4rem)] font-normal leading-[1.06] tracking-[-0.04em] text-ink-900"
              initial={{ opacity: 0, y: shouldReduce ? 0 : 26 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.3 }}
            >
              {title}
            </motion.h1>

            {blurb && (
              <motion.p
                className="mt-6 max-w-[46ch] font-body text-base leading-8 text-ink-600"
                initial={{ opacity: 0, y: shouldReduce ? 0 : 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.45 }}
              >
                {blurb}
              </motion.p>
            )}

            {bullets.length > 0 && (
              <motion.ul
                className="mt-10 flex flex-col gap-4"
                initial="hidden"
                animate="show"
                transition={{ staggerChildren: 0.1, delayChildren: 0.6 }}
              >
                {bullets.map(({ icon, title: bulletTitle, note }) => (
                  <motion.li
                    key={bulletTitle}
                    variants={{
                      hidden: { opacity: 0, x: shouldReduce ? 0 : -16 },
                      show: { opacity: 1, x: 0 },
                    }}
                    className="flex items-start gap-4"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-gold-600/30 bg-white text-gold-700">
                      <span className="material-symbols-outlined text-base">{icon}</span>
                    </span>
                    <span className="flex flex-col">
                      <span className="font-body text-xs font-bold uppercase tracking-[0.16em] text-ink-800">
                        {bulletTitle}
                      </span>
                      <span className="mt-1 font-body text-sm leading-6 text-ink-600">{note}</span>
                    </span>
                  </motion.li>
                ))}
              </motion.ul>
            )}

            {footnote && (
              <p className="mt-10 font-body text-xs leading-5 text-ink-500">{footnote}</p>
            )}
          </div>
        </section>

        {/* Form stage */}
        <section className="relative flex flex-1 items-center justify-center px-5 py-16 sm:px-8 sm:py-20 lg:w-1/2 lg:py-24">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-40"
            style={{
              background:
                'radial-gradient(60% 45% at 80% 8%, rgba(233,193,118,0.16) 0%, rgba(251,250,247,0) 70%)',
            }}
          />
          <motion.div
            className="relative w-full max-w-[440px]"
            initial={{ opacity: 0, y: shouldReduce ? 0 : 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.25 }}
          >
            {children}
          </motion.div>
        </section>
      </main>
    </div>
  );
};

export default AuthLayout;
