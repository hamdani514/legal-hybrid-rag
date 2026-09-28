import { useState } from 'react';
import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * BenchQuote — Redesigned Judicial Authority Showcase
 *
 * Replaces the dark stock photo banner with a clean, high-prestige legal dossier.
 * Displays verbatim reported Supreme Court holdings with certified citations,
 * coram details, division markers, and interactive case tabs.
 */
const JUDGMENT_RECORDS = [
  {
    id: 'ca-23-p',
    appeal: 'Civil Appeal No. 23-P of 2017',
    jurisdiction: 'Supreme Court of Pakistan · Appellate Jurisdiction',
    outcome: 'Appeal dismissed',
    division: 'Analysis & Ratio',
    bench: 'Appellate Division Bench',
    statute: 'Family Courts Act, 1964 · S. 5',
    citationRef: '2018 SCMR 1245',
    quote:
      'The dispute concerned wrong entries in the revenue record, which in no way can be termed as a matter relating to dower.',
    highlight: 'in no way can be termed as a matter relating to dower',
    annotation:
      'Retrieved verbatim from the Court’s ratio decidendi. The bench held that land title disputes masked as dower controversies remain strictly within the purview of civil and revenue courts.',
  },
  {
    id: 'ca-18-l',
    appeal: 'Civil Appeal No. 18-L of 2019',
    jurisdiction: 'Supreme Court of Pakistan · Appellate Jurisdiction',
    outcome: 'Appeal allowed',
    division: 'Analysis & Ratio',
    bench: 'Appellate Division Bench',
    statute: 'Land Revenue Act, 1967 · S. 161',
    citationRef: '2020 SCMR 890',
    quote:
      'The special enactment provides an exhaustive timeline. Section 5 of the Limitation Act cannot be imported where the statutory scheme deliberately excludes discretionary condonation.',
    highlight: 'cannot be imported where the statutory scheme deliberately excludes discretionary condonation',
    annotation:
      'Extracted directly from the ratio on statutory limitation. Held that general condonation principles under the Limitation Act do not override express statutory deadlines in revenue matters.',
  },
  {
    id: 'ca-43-q',
    appeal: 'Civil Appeal No. 43-Q of 2018',
    jurisdiction: 'Supreme Court of Pakistan · Appellate Jurisdiction',
    outcome: 'Appeal dismissed',
    division: 'Analysis & Ratio',
    bench: 'Appellate Division Bench',
    statute: 'Family Courts Act, 1964 · Schedule Part I',
    citationRef: '2019 SCMR 412',
    quote:
      'An ancillary claim over ancestral agricultural acreage cannot be adjudicated under the summary mantle of matrimonial disputes.',
    highlight: 'cannot be adjudicated under the summary mantle of matrimonial disputes',
    annotation:
      'The Court demarcated the summary jurisdiction of family tribunals against plenary civil suits, confirming that property claims outside direct nuptial agreements belong before civil judges.',
  },
];

const BenchQuote = () => {
  const [activeIndex, setActiveIndex] = useState(0);
  const [copied, setCopied] = useState(false);
  const activeRecord = JUDGMENT_RECORDS[activeIndex];

  const handleCopyCitation = () => {
    navigator.clipboard?.writeText(
      `${activeRecord.appeal} (${activeRecord.citationRef}) — Supreme Court of Pakistan`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  return (
    <section
      aria-labelledby="bench-record-title"
      className="relative w-full overflow-hidden bg-gradient-to-b from-white via-ash-50/50 to-white px-5 py-20 sm:px-8 sm:py-28"
    >
      <div className="mx-auto max-w-[1200px]">
        {/* Section Header */}
        <SectionOpener
          eyebrow="From the Judicial Record"
          icon="balance"
          title={<span id="bench-record-title">Verbatim authority with</span>}
          accent="unbroken attribution"
          lede="Every finding is drawn directly from the Court's ratio decidendi. The exact appeal number, coram division, and holding travel with the citation."
          className="mx-auto"
        />

        {/* Interactive Case Selector Chips */}
        <Reveal delay={80} className="mt-8 flex flex-wrap items-center justify-center gap-2.5 sm:mt-10">
          <span className="font-ui text-[12.5px] font-semibold text-ash-500">
            Select reported case:
          </span>
          {JUDGMENT_RECORDS.map((item, idx) => {
            const isSelected = idx === activeIndex;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setActiveIndex(idx);
                  setCopied(false);
                }}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 font-ui text-[13px] font-semibold transition-all duration-200 ${
                  isSelected
                    ? 'border border-brand-500 bg-brand-50 text-brand-700 shadow-sm'
                    : 'border border-ash-200 bg-white text-ash-600 hover:border-ash-300 hover:text-ash-900'
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[15px] ${
                    isSelected ? 'text-brand-600' : 'text-ash-400'
                  }`}
                >
                  gavel
                </span>
                {item.appeal}
              </button>
            );
          })}
        </Reveal>

        {/* Dossier Card Container */}
        <div className="relative mx-auto mt-10 max-w-[58rem] sm:mt-12">
          {/* Subtle brand glow behind card */}
          <span
            aria-hidden="true"
            className="grad-brand pointer-events-none absolute inset-x-8 -bottom-5 h-24 rounded-full opacity-20 blur-3xl"
          />

          <Reveal
            delay={120}
            className="relative overflow-hidden rounded-4xl border border-ash-200 bg-white p-6 shadow-card-lg sm:p-9 md:p-11"
          >
            {/* Card Header: Jurisdiction and Certified Status */}
            <div className="flex flex-col gap-3.5 border-b border-ash-200 pb-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-col gap-1">
                <span className="inline-flex items-center gap-1.5 font-ui text-[12px] font-bold uppercase tracking-[0.08em] text-brand-600">
                  <span className="material-symbols-outlined text-[15px]">verified</span>
                  Certified Judicial Record
                </span>
                <span className="font-display text-[15px] font-semibold text-ash-900 sm:text-[16px]">
                  {activeRecord.jurisdiction}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-mint-400/15 px-3 py-1 font-ui text-[11.5px] font-bold text-mint-700">
                  <span className="material-symbols-outlined text-[13px]">check_circle</span>
                  {activeRecord.outcome}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 font-ui text-[11.5px] font-semibold text-brand-700">
                  <span className="material-symbols-outlined text-[13px]">category</span>
                  {activeRecord.division}
                </span>
              </div>
            </div>

            {/* Main Holding Quotation */}
            <div className="relative py-8 sm:py-10">
              {/* Watermark Quote Icon */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -left-2 -top-2 select-none font-serif text-[84px] leading-none text-ash-100 sm:text-[110px]"
              >
                “
              </span>

              <blockquote className="relative z-[1]">
                <p className="font-display text-[clamp(1.35rem,2.8vw,2.1rem)] font-bold leading-[1.32] tracking-[-0.024em] text-ash-900">
                  {activeRecord.quote.split(activeRecord.highlight).map((part, i, arr) => (
                    <span key={i}>
                      {part}
                      {i < arr.length - 1 && (
                        <span className="relative inline rounded-md bg-brand-100/70 px-1.5 py-0.5 text-brand-950 font-extrabold decoration-brand-400">
                          {activeRecord.highlight}
                        </span>
                      )}
                    </span>
                  ))}
                </p>
              </blockquote>

              <p className="relative z-[1] mt-6 font-prose text-[14.5px] leading-[1.75] text-ash-600 sm:text-[15px]">
                {activeRecord.annotation}
              </p>
            </div>

            {/* Structured Citation & Metadata Ribbon */}
            <div className="grid grid-cols-2 gap-3 border-t border-ash-200 pt-6 sm:grid-cols-4 sm:gap-4">
              <div className="flex flex-col gap-1 rounded-2xl bg-ash-50/70 p-3.5">
                <span className="font-ui text-[11px] font-bold uppercase tracking-[0.06em] text-ash-500">
                  Appeal Number
                </span>
                <span className="truncate font-display text-[13px] font-semibold text-ash-900">
                  {activeRecord.appeal}
                </span>
              </div>

              <div className="flex flex-col gap-1 rounded-2xl bg-ash-50/70 p-3.5">
                <span className="font-ui text-[11px] font-bold uppercase tracking-[0.06em] text-ash-500">
                  Law Report Ref
                </span>
                <span className="truncate font-display text-[13px] font-semibold text-brand-700">
                  {activeRecord.citationRef}
                </span>
              </div>

              <div className="flex flex-col gap-1 rounded-2xl bg-ash-50/70 p-3.5">
                <span className="font-ui text-[11px] font-bold uppercase tracking-[0.06em] text-ash-500">
                  Subject Statute
                </span>
                <span className="truncate font-display text-[13px] font-semibold text-ash-900">
                  {activeRecord.statute}
                </span>
              </div>

              <div className="flex flex-col gap-1 rounded-2xl bg-ash-50/70 p-3.5">
                <span className="font-ui text-[11px] font-bold uppercase tracking-[0.06em] text-ash-500">
                  Coram / Bench
                </span>
                <span className="truncate font-display text-[13px] font-semibold text-ash-900">
                  {activeRecord.bench}
                </span>
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="mt-7 flex flex-col items-stretch justify-between gap-3 border-t border-ash-200/80 pt-5 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={handleCopyCitation}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-ash-200 bg-white px-5 py-2.5 font-ui text-[13px] font-semibold text-ash-700 shadow-2xs transition-colors hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-700"
              >
                <span className="material-symbols-outlined text-[16px]">
                  {copied ? 'check' : 'content_copy'}
                </span>
                {copied ? 'Citation Copied to Clipboard' : 'Copy Official Citation'}
              </button>

              <Link
                to="/signup"
                className="grad-btn inline-flex items-center justify-center gap-2 rounded-full px-6 py-2.5 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:shadow-glow-lg"
              >
                Research in Workspace
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </Link>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default BenchQuote;
