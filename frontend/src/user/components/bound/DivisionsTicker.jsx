/**
 * DivisionsTicker
 * Continuous marquee slider displaying the six judgment divisions
 * (Header & Coram, Facts, Arguments, Legal Issues, Analysis & Ratio, Final Order)
 * seamlessly cycling directly beneath the hero banner.
 */
const DIVISIONS = [
  'Header & Coram',
  'Facts',
  'Arguments',
  'Legal Issues',
  'Analysis & Ratio',
  'Final Order',
];

// Repeating enough times so the marquee seamlessly spans and loops on all screen sizes (up to 4K)
const BASE_SET = [...DIVISIONS, ...DIVISIONS];
const TICKER_ITEMS = [...BASE_SET, ...BASE_SET];

const DivisionsTicker = ({ className = '' }) => {
  return (
    <div
      aria-label="Judgment divisions indexed"
      className={`marquee-mask relative w-full overflow-hidden border-y border-ash-200 bg-white py-4 sm:py-5 shadow-2xs ${className}`.trim()}
    >
      <ul className="marquee-track flex items-center gap-10 sm:gap-14">
        {TICKER_ITEMS.map((label, index) => (
          <li
            key={`${label}-${index}`}
            className="flex shrink-0 items-center gap-3"
            aria-hidden={index >= DIVISIONS.length ? 'true' : undefined}
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-brand-600 shadow-2xs"
            >
              <span className="material-symbols-outlined text-[15px] font-bold">check</span>
            </span>
            <span className="whitespace-nowrap font-display text-[14px] font-semibold tracking-[-0.01em] text-ash-700">
              {label}
            </span>
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-ash-300" />
          </li>
        ))}
      </ul>
    </div>
  );
};

export default DivisionsTicker;
