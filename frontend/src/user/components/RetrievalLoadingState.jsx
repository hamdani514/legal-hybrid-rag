import { useState, useEffect } from 'react';
import { LoadingDots } from './TypedText';

// What the search is doing, alternating while it runs: finding the judgments,
// then reading them against the question.
const STAGES = ['Fetching', 'Analyzing'];
const STAGE_MS = 2200;

const RetrievalLoadingState = () => {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % STAGES.length);
    }, STAGE_MS);
    return () => clearInterval(timer);
  }, []);

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
          <span className="font-display text-[15px] font-semibold text-ash-900">Verdict AI</span>

          {/* Sleek Gradient Progress Bar */}
          <div className="w-full max-w-md h-1.5 bg-ash-100 rounded-full overflow-hidden relative border border-ash-200/40">
            <div className="absolute top-0 bottom-0 rounded-full bg-gradient-to-r from-brand-600 via-cyan-400 to-indigo-600 animate-retrieval-bar" />
          </div>

          {/* Fetching... / Analyzing... */}
          <LoadingDots
            key={stageIndex}
            label={STAGES[stageIndex]}
            className="animate-[fadeIn_0.3s_ease-out] font-prose text-[15px] font-medium text-ash-700"
          />
        </div>
      </div>
    </div>
  );
};

export default RetrievalLoadingState;
