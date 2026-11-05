import MediaFrame from './bound/MediaFrame';
import FilterIcon from './FilterIcon';

/**
 * The workspace before the first search. The cards and chips say what the
 * workspace is for; they are not controls. The cards animate on hover, but a
 * click does nothing: it used to send a canned question, which spent one of
 * the user's daily searches by accident.
 */
const EmptyState = () => {
  const cards = [
    {
      title: 'Analyze Statute',
      description: 'Find the Supreme Court judgments that interpret a statute or a section, and read what the Court held.',
      icon: 'scale',
      media: 'scales',
    },
    {
      title: 'Precedent Review',
      description: 'Retrieve the precedents closest to your facts and read the Court’s own reasoning.',
      icon: 'account_balance',
      media: 'volume',
    },
    {
      title: 'Drafting Support',
      description: 'Collect the authorities for your brief, with their case numbers and decisions, ready to copy.',
      icon: 'edit_note',
      media: 'desk',
    },
  ];

  const chips = [
    { text: 'Download relevant precedents', icon: 'download' },
    { text: 'Compare multiple precedents', icon: 'compare_arrows' },
    { text: 'Analyze precedents', icon: 'auto_awesome' },
    { text: 'Filter precedents', icon: 'filter' },
  ];

  return (
    <div className="flex-grow flex flex-col items-center justify-center max-w-4xl mx-auto px-4 sm:px-8 pt-20 sm:pt-24 pb-44 w-full select-none animate-[fadeIn_0.5s_ease-out]">
      {/* Welcome Section */}
      <div className="text-center mb-16">
        <h2 className="font-display text-4xl sm:text-5xl md:text-6xl text-ash-900 mb-6 tracking-tight leading-tight">
          How can I assist your <span className="serif-italic">research</span> today?
        </h2>
        <p className="text-ash-600 text-lg max-w-2xl mx-auto font-prose leading-relaxed">
          Access the collective intelligence of Verdict AI. From statute interpretation to landmark precedent analysis, our workspace is designed for high-stakes accuracy.
        </p>
      </div>

      {/* Bento Grid Suggested Points */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
        {cards.map((card, idx) => (
          <div
            key={idx}
            className="lift-card border-trace group flex flex-col justify-between overflow-hidden rounded-3xl border border-ash-200/70 bg-white shadow-soft transition-all duration-300 hover:border-brand-300/60 hover:shadow-card"
          >
            <MediaFrame name={card.media} ratio="16 / 7" wash="ink" zoom className="sheen w-full">
              <span
                aria-hidden="true"
                className="absolute bottom-4 left-5 z-[2] flex h-10 w-10 items-center justify-center rounded-2xl border border-white/25 bg-white/15 text-white backdrop-blur-md"
              >
                <span className="material-symbols-outlined text-[20px]">{card.icon}</span>
              </span>
            </MediaFrame>

            <div className="p-7">
              <h3 className="font-display text-xl text-ash-900 mb-2">{card.title}</h3>
              <p className="text-sm text-ash-600 leading-relaxed">{card.description}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tips / Guidance */}
      <div className="mt-12 flex flex-wrap justify-center gap-x-3 gap-y-3">
        {chips.map((chip, idx) => (
          <div
            key={idx}
            className="flex items-center gap-2 text-xs text-ash-500 bg-brand-50 px-4 py-2 rounded-full border border-ash-200/50"
          >
            {chip.icon === 'filter' ? (
              <FilterIcon size={13} />
            ) : (
              <span aria-hidden="true" className="material-symbols-outlined text-sm">{chip.icon}</span>
            )}
            <span>{chip.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EmptyState;
