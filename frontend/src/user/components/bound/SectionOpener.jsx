import Reveal from '../Reveal';

/**
 * The standard section opener: a pill eyebrow with an icon, a large Outfit
 * headline where one phrase carries the brand gradient, and a lede.
 *
 * `accent` is the phrase inside `title` to gradient — pass the title as
 * `['Built for the way ', 'research runs']` and the second half gradients.
 */
const SectionOpener = ({
  eyebrow,
  icon = 'auto_awesome',
  title,
  accent,
  lede,
  align = 'center',
  tone = 'light',
  className = '',
}) => {
  const centered = align === 'center';
  const dark = tone === 'dark';

  return (
    <header
      className={`flex flex-col ${centered ? 'items-center text-center' : 'items-start text-left'} ${className}`.trim()}
    >
      {eyebrow && (
        <Reveal variant="fade">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 font-ui text-[12.5px] font-semibold ${
              dark
                ? 'border-white/20 bg-white/10 text-brand-100'
                : 'border-brand-100 bg-brand-50 text-brand-700'
            }`}
          >
            <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
              {icon}
            </span>
            {eyebrow}
          </span>
        </Reveal>
      )}

      <Reveal
        as="h2"
        delay={80}
        className={`mt-6 font-display text-[clamp(2rem,4.8vw,3.25rem)] font-bold leading-[1.1] tracking-[-0.03em] text-balance ${
          dark ? 'text-white' : 'text-ash-900'
        }`}
      >
        {title}
        {accent && (
          <>
            {' '}
            <span className={dark ? 'text-brand-300' : 'grad-text'}>{accent}</span>
          </>
        )}
      </Reveal>

      {lede && (
        <Reveal
          as="p"
          delay={160}
          className={`mt-5 max-w-[46rem] font-prose text-[1.0625rem] leading-[1.75] sm:text-lg ${
            dark ? 'text-brand-100/85' : 'text-ash-600'
          }`}
        >
          {lede}
        </Reveal>
      )}
    </header>
  );
};

export default SectionOpener;
