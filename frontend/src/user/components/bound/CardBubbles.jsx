/**
 * CardBubbles — Floating Organic Glass Bubbles
 *
 * Renders translucent, overlapping circular bubbles that drift in random paths
 * inside card containers. Modeled after the reference inspiration to create
 * deep organic dimensionality and lively background motion.
 */
const CardBubbles = ({ tone = 'light', density = 'standard', className = '' }) => {
  const isLight = tone === 'light';

  if (density === 'compact') {
    return (
      <div
        className={`pointer-events-none absolute inset-0 overflow-hidden select-none ${className}`}
        aria-hidden="true"
      >
        {/* Bubble 1: Top-Right */}
        <span
          className={`bubble-drift-1 absolute -right-12 -top-12 h-44 w-44 rounded-full border ${
            isLight
              ? 'border-white/20 bg-white/[0.07] shadow-[inset_0_0_20px_rgba(255,255,255,0.12)]'
              : 'border-brand-300/30 bg-brand-500/[0.04]'
          }`}
        />

        {/* Bubble 2: Bottom-Right */}
        <span
          className={`bubble-drift-2 absolute -bottom-10 right-4 h-32 w-32 rounded-full border ${
            isLight
              ? 'border-white/25 bg-white/[0.08] shadow-[inset_0_0_16px_rgba(255,255,255,0.14)]'
              : 'border-brand-300/30 bg-brand-500/[0.05]'
          }`}
        />

        {/* Bubble 3: Center-Left */}
        <span
          className={`bubble-drift-3 absolute -left-10 top-1/3 h-36 w-36 rounded-full border ${
            isLight
              ? 'border-white/15 bg-white/[0.06] shadow-[inset_0_0_18px_rgba(255,255,255,0.10)]'
              : 'border-brand-300/25 bg-brand-500/[0.03]'
          }`}
        />

        {/* Bubble 4: Bottom-Left accent */}
        <span
          className={`bubble-drift-5 absolute bottom-6 left-1/4 h-20 w-20 rounded-full border ${
            isLight
              ? 'border-white/30 bg-white/[0.10] shadow-[inset_0_0_12px_rgba(255,255,255,0.18)]'
              : 'border-brand-300/35 bg-brand-500/[0.06]'
          }`}
        />
      </div>
    );
  }

  return (
    <div
      className={`pointer-events-none absolute inset-0 overflow-hidden select-none ${className}`}
      aria-hidden="true"
    >
      {/* Bubble 1: Large primary bubble behind title/right */}
      <span
        className={`bubble-drift-1 absolute -right-14 -top-14 h-80 w-80 rounded-full border sm:h-96 sm:w-96 ${
          isLight
            ? 'border-white/20 bg-white/[0.07] shadow-[inset_0_0_35px_rgba(255,255,255,0.12)]'
            : 'border-brand-200/50 bg-brand-500/[0.04]'
        }`}
      />

      {/* Bubble 2: Medium bubble floating lower right */}
      <span
        className={`bubble-drift-2 absolute -bottom-16 right-[12%] h-60 w-60 rounded-full border sm:h-72 sm:w-72 ${
          isLight
            ? 'border-white/25 bg-white/[0.08] shadow-[inset_0_0_28px_rgba(255,255,255,0.14)]'
            : 'border-brand-200/60 bg-brand-500/[0.05]'
        }`}
      />

      {/* Bubble 3: Large bubble drifting on the left side */}
      <span
        className={`bubble-drift-3 absolute -left-20 top-[18%] h-72 w-72 rounded-full border sm:h-84 sm:w-84 ${
          isLight
            ? 'border-white/15 bg-white/[0.06] shadow-[inset_0_0_30px_rgba(255,255,255,0.10)]'
            : 'border-brand-200/40 bg-brand-500/[0.03]'
        }`}
      />

      {/* Bubble 4: Crisp medium bubble at bottom left */}
      <span
        className={`bubble-drift-4 absolute bottom-6 left-[18%] h-44 w-44 rounded-full border sm:h-52 sm:w-52 ${
          isLight
            ? 'border-white/25 bg-white/[0.09] shadow-[inset_0_0_22px_rgba(255,255,255,0.16)]'
            : 'border-brand-200/50 bg-brand-500/[0.05]'
        }`}
      />

      {/* Bubble 5: Small bright accent bubble near top center */}
      <span
        className={`bubble-drift-5 absolute top-10 left-[42%] h-28 w-28 rounded-full border sm:h-36 sm:w-36 ${
          isLight
            ? 'border-white/30 bg-white/[0.12] shadow-[inset_0_0_18px_rgba(255,255,255,0.20)]'
            : 'border-brand-300/60 bg-brand-500/[0.07]'
        }`}
      />

      {/* Bubble 6: Tiny floating orb near bottom right */}
      <span
        className={`bubble-drift-6 absolute bottom-12 right-[36%] h-20 w-20 rounded-full border sm:h-24 sm:w-24 ${
          isLight
            ? 'border-white/35 bg-white/[0.14] shadow-[inset_0_0_14px_rgba(255,255,255,0.22)]'
            : 'border-brand-300/70 bg-brand-500/[0.08]'
        }`}
      />
    </div>
  );
};

export default CardBubbles;
