import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import MediaFrame from './MediaFrame';

/**
 * One photograph, one argument, side by side — the row the site uses whenever
 * a claim is better shown than listed.
 *
 * `flip` puts the photograph on the right. The two rows that use it alternate,
 * which is what stops a run of them reading as a template.
 *
 * The overlay card is deliberately anchored to the photograph's bottom-left
 * and allowed to hang past its edge at desktop width: it ties the two columns
 * together, so the row reads as one object instead of a picture beside a
 * paragraph.
 */
const SplitFeature = ({
  media,
  kicker,
  icon = 'auto_awesome',
  title,
  accent,
  body,
  points = [],
  overlay,
  cta,
  flip = false,
  ratio = '4 / 5',
}) => {
  return (
    <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2 lg:gap-16">
      {/* ── Photograph ───────────────────────────────────────────────── */}
      <Reveal
        variant={flip ? 'right' : 'left'}
        className={`group relative ${flip ? 'lg:order-2' : ''}`}
      >
        <span
          aria-hidden="true"
          className={`grad-brand pointer-events-none absolute -bottom-6 h-24 rounded-full opacity-25 blur-3xl ${
            flip ? 'left-8 right-4' : 'left-4 right-8'
          }`}
        />

        <MediaFrame
          name={media}
          ratio={ratio}
          wash="base"
          zoom
          className="ring-photo relative rounded-4xl shadow-card-lg"
        />

        {/* The hanging card. Hidden below lg, where it would cover the
            photograph rather than sit against it. */}
        {overlay && (
          <div
            className={`absolute -bottom-8 z-[3] hidden w-[19rem] rounded-3xl border border-ash-200 bg-white/95 p-5 shadow-card-lg backdrop-blur-md lg:block ${
              flip ? '-left-10' : '-right-10'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className="grad-brand flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow"
              >
                <span className="material-symbols-outlined text-[18px]">{overlay.icon}</span>
              </span>
              <span className="font-display text-[13.5px] font-bold text-ash-900">
                {overlay.title}
              </span>
            </div>

            <p className="mt-3.5 font-prose text-[13px] leading-[1.65] text-ash-600">
              {overlay.body}
            </p>

            {overlay.tag && (
              <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-mint-400/15 px-3 py-1 font-ui text-[11px] font-bold text-mint-700">
                <span aria-hidden="true" className="material-symbols-outlined text-[13px]">
                  check_circle
                </span>
                {overlay.tag}
              </span>
            )}
          </div>
        )}
      </Reveal>

      {/* ── Argument ─────────────────────────────────────────────────── */}
      <div className={flip ? 'lg:order-1' : ''}>
        {kicker && (
          <Reveal variant="fade">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700">
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                {icon}
              </span>
              {kicker}
            </span>
          </Reveal>
        )}

        <Reveal
          as="h3"
          delay={80}
          className="mt-6 font-display text-[clamp(1.75rem,3.6vw,2.5rem)] font-bold leading-[1.12] tracking-[-0.028em] text-balance text-ash-900"
        >
          {title} {accent && <span className="grad-text">{accent}</span>}
        </Reveal>

        <Reveal
          as="p"
          delay={150}
          className="mt-5 max-w-[34rem] font-prose text-[1.0625rem] leading-[1.8] text-ash-600"
        >
          {body}
        </Reveal>

        {points.length > 0 && (
          <ul className="mt-8 flex flex-col gap-4">
            {points.map(({ icon: pointIcon, title: pointTitle, note }, index) => (
              <Reveal
                as="li"
                key={pointTitle}
                variant="fade"
                delay={220 + index * 80}
                className="group/point flex items-start gap-3.5"
              >
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover/point:bg-brand-500 group-hover/point:text-white"
                >
                  <span className="material-symbols-outlined text-[18px]">{pointIcon}</span>
                </span>
                <span className="flex flex-col">
                  <span className="font-display text-[14.5px] font-bold text-ash-900">
                    {pointTitle}
                  </span>
                  <span className="mt-1 max-w-[32rem] font-prose text-[13.5px] leading-[1.65] text-ash-600">
                    {note}
                  </span>
                </span>
              </Reveal>
            ))}
          </ul>
        )}

        {cta && (
          <Reveal variant="fade" delay={420} className="mt-9">
            <Link
              to={cta.to}
              className="group/cta inline-flex items-center gap-2 font-ui text-[14.5px] font-bold text-brand-700 transition-colors duration-300 hover:text-brand-800"
            >
              {cta.label}
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover/cta:translate-x-1"
              >
                arrow_forward
              </span>
            </Link>
          </Reveal>
        )}
      </div>
    </div>
  );
};

export default SplitFeature;
