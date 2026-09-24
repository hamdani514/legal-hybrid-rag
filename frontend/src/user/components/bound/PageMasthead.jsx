import Reveal from '../Reveal';
import MediaFrame from './MediaFrame';

/**
 * The masthead that opens About, Contact and FAQ. Light ground with a blue
 * bloom, a pill kicker, a large headline whose closing phrase carries the
 * gradient, and a row of stat pills.
 *
 * `media` adds a wide photographic plate beneath the stat row — a key into
 * MEDIA. It is optional because not every page wants one: Contact opens onto
 * a form, and a photograph there would only push the first field down. Where
 * it is used, the plate is what hands the reader off to the section below,
 * so the masthead's bottom padding drops to make the join tight.
 */
const PageMasthead = ({
  kicker,
  icon = 'auto_awesome',
  title,
  accent,
  lede,
  meta = [],
  media,
  mediaCaption,
  mediaRatio = false,
}) => {
  return (
    <header className="ground-light relative w-full overflow-hidden">
      {/* Soft floating blooms, decorative only. */}
      <span
        aria-hidden="true"
        className="float-y-slow pointer-events-none absolute -right-24 top-10 h-72 w-72 rounded-full bg-brand-200/30 blur-3xl"
      />
      <span
        aria-hidden="true"
        className="float-y pointer-events-none absolute -left-24 bottom-0 h-64 w-64 rounded-full bg-violet-600/10 blur-3xl"
      />

      <div className={`relative mx-auto flex w-full max-w-[1200px] flex-col items-center px-5 pt-32 text-center sm:px-8 sm:pt-36 lg:pt-40 ${
          media ? 'pb-0' : 'pb-20 sm:pb-24 lg:pb-28'
        }`}>
        {kicker && (
          <span
            className="pop-in inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700"
            style={{ '--i': 0 }}
          >
            <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
              {icon}
            </span>
            {kicker}
          </span>
        )}

        <h1
          className="pop-in mt-7 max-w-[54rem] font-display text-[clamp(2.4rem,6.4vw,4.25rem)] font-bold leading-[1.05] tracking-[-0.035em] text-balance text-ash-900"
          style={{ '--i': 1 }}
        >
          {title}
          {accent && (
            <>
              {' '}
              <span className="grad-text">{accent}</span>
            </>
          )}
        </h1>

        {lede && (
          <p
            className="pop-in mt-7 max-w-[44rem] font-prose text-[1.0625rem] leading-[1.8] text-ash-600 sm:text-lg"
            style={{ '--i': 2 }}
          >
            {lede}
          </p>
        )}

        {meta.length > 0 && (
          <dl
            className="pop-in mt-11 flex flex-wrap items-center justify-center gap-3"
            style={{ '--i': 3 }}
          >
            {meta.map(({ label, value }) => (
              <div
                key={label}
                className="flex items-center gap-2.5 rounded-full border border-ash-200 bg-white px-5 py-2.5 shadow-soft"
              >
                <dt className="font-ui text-[12px] font-medium text-ash-500">{label}</dt>
                <dd className="font-display text-[13.5px] font-bold text-ash-900">{value}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* ── Photographic plate ─────────────────────────────────────── */}
        {media && (
          <Reveal variant="fade" className="mt-14 w-full sm:mt-16">
            <div className="group relative">
              <span
                aria-hidden="true"
                className="grad-brand pointer-events-none absolute inset-x-12 -bottom-5 h-24 rounded-full opacity-25 blur-3xl"
              />

              <MediaFrame
                name={media}
                ratio={mediaRatio}
                wash="base"
                zoom
                grain
                className="media-plate ring-photo clip-up relative rounded-4xl shadow-card-lg"
              >
                {mediaCaption && (
                  <figcaption className="absolute inset-x-0 bottom-0 z-[2] flex flex-wrap items-center justify-center gap-x-3 gap-y-2 px-6 pb-6 text-center sm:pb-8">
                    <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/15 px-4 py-1.5 font-ui text-[12px] font-semibold text-white backdrop-blur-md">
                      <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                        photo_camera
                      </span>
                      {mediaCaption}
                    </span>
                  </figcaption>
                )}
              </MediaFrame>
            </div>
          </Reveal>
        )}
      </div>
    </header>
  );
};

export default PageMasthead;
