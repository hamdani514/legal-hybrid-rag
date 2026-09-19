
const EmptyState = ({ onSelectCard }) => {
  const cards = [
    {
      title: 'Analyze Statute',
      description: 'Extract core implications and legislative intent from complex regulatory frameworks.',
      icon: 'scale',
      prompt: 'Analyze the statute implications for corporate tax governance in the current framework.',
    },
    {
      title: 'Precedent Review',
      description: 'Identify landmark rulings and dissenting opinions relevant to your current brief.',
      icon: 'account_balance',
      prompt: 'Summarize key precedents and dissenting opinions on civil liability and digital rights.',
    },
    {
      title: 'Drafting Support',
      description: 'Refine arguments and ensure citation accuracy across multiple jurisdictions.',
      icon: 'edit_note',
      prompt: 'Help me draft an argument summary addressing cross-jurisdictional contract breaches.',
    },
  ];

  const chips = [
    { text: 'Use specific jurisdiction names', icon: 'lightbulb' },
    { text: 'Upload case files for analysis', icon: 'attachment' },
    { text: 'Summarize historical timelines', icon: 'timer' },
  ];

  return (
    <div className="flex-grow flex flex-col items-center justify-center max-w-4xl mx-auto px-8 pt-24 pb-44 w-full select-none animate-[fadeIn_0.5s_ease-out]">
      {/* Welcome Section */}
      <div className="text-center mb-16">
        <h2 className="font-display text-5xl md:text-6xl text-ash-900 mb-6 tracking-tight leading-tight">
          How can I assist your <span className="serif-italic">research</span> today?
        </h2>
        <p className="text-ash-600 text-lg max-w-2xl mx-auto font-prose leading-relaxed">
          Access the collective intelligence of the Atelier. From statute interpretation to landmark precedent analysis, our workspace is designed for high-stakes accuracy.
        </p>
      </div>

      {/* Bento Grid Suggested Points */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
        {cards.map((card, idx) => (
          <div
            key={idx}
            onClick={() => onSelectCard(card.prompt)}
            className="group bg-ash-50 p-8 rounded-none border border-ash-200/70 hover:border-brand-300/50 hover:bg-ash-100 hover:shadow-sm transition-all duration-300 cursor-pointer flex flex-col justify-between"
          >
            <div>
              <span className="material-symbols-outlined text-brand-500 mb-4 block text-3xl">
                {card.icon}
              </span>
              <h3 className="font-display text-xl text-ash-900 mb-2">{card.title}</h3>
              <p className="text-sm text-ash-600 leading-relaxed">{card.description}</p>
            </div>
            <div className="mt-8 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center text-xs font-semibold text-brand-500 uppercase tracking-widest">
              Start Session{' '}
              <span className="material-symbols-outlined text-sm ml-1">arrow_forward</span>
            </div>
          </div>
        ))}
      </div>

      {/* Tips / Guidance */}
      <div className="mt-12 flex flex-wrap justify-center gap-x-8 gap-y-4">
        {chips.map((chip, idx) => (
          <div
            key={idx}
            className="flex items-center gap-2 text-xs text-ash-500 bg-brand-50 px-4 py-2 rounded-full border border-ash-200/50"
          >
            <span className="material-symbols-outlined text-sm">{chip.icon}</span>
            <span>{chip.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EmptyState;
