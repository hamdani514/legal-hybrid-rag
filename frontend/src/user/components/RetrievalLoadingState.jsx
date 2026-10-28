import { useState, useEffect } from 'react';

const STAGES = [
  { text: 'Scanning reported Supreme Court judgments…', icon: 'travel_explore' },
  { text: 'Matching query across semantic nodes & precedent database…', icon: 'hub' },
  { text: 'Extracting ratio decidendi & relevant case holdings…', icon: 'balance' },
  { text: 'Synthesizing authorities and preparing judicial brief…', icon: 'auto_awesome' },
];

const RetrievalLoadingState = () => {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % STAGES.length);
    }, 2400);
    return () => clearInterval(timer);
  }, []);

  const currentStage = STAGES[stageIndex];

  return (
    <div className="flex justify-start w-full animate-[fadeIn_0.3s_ease-out]">
      <div className="w-full max-w-2xl flex gap-4">
        {/* Glowing Logo Avatar */}
        <div className="relative shrink-0 mt-1">
          <div className="h-9 w-9 rounded-2xl bg-gradient-to-tr from-brand-600 via-brand-500 to-cyan-500 flex items-center justify-center text-white shadow-soft">
            <span className="material-symbols-outlined text-[19px]">gavel</span>
          </div>
          <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500 ring-2 ring-white" />
          </span>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="font-display text-[15px] font-semibold text-ash-900">Verdict AI</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-brand-50 text-brand-700 border border-brand-200/60 font-ui">
              <span className="material-symbols-outlined text-[13px] animate-spin text-brand-600">
                sync
              </span>
              <span>Researching precedents</span>
            </span>
          </div>

          {/* Sleek Gradient Progress Bar */}
          <div className="w-full max-w-md h-1.5 bg-ash-100 rounded-full overflow-hidden relative border border-ash-200/40">
            <div className="absolute top-0 bottom-0 rounded-full bg-gradient-to-r from-brand-600 via-cyan-400 to-indigo-600 animate-retrieval-bar" />
          </div>

          {/* Cycling Status Phase */}
          <div className="flex items-center gap-2 text-xs font-prose text-ash-600 mt-0.5 transition-all duration-300">
            <span className="material-symbols-outlined text-[15px] text-cyan-600 shrink-0">
              {currentStage.icon}
            </span>
            <span className="truncate">{currentStage.text}</span>
          </div>

          {/* Shimmer Skeleton Card */}
          <div className="mt-2 rounded-2xl border border-ash-200/80 bg-white/70 p-5 shadow-soft flex flex-col gap-3 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="h-4 w-28 bg-ash-200/70 rounded-full animate-pulse" />
              <div className="h-4 w-16 bg-ash-100 rounded-full animate-pulse" />
            </div>
            <div className="space-y-2">
              <div className="h-3 w-5/6 bg-ash-100 rounded-full animate-pulse" />
              <div className="h-3 w-full bg-ash-100/80 rounded-full animate-pulse" />
              <div className="h-3 w-4/6 bg-ash-100/60 rounded-full animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RetrievalLoadingState;
