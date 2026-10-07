import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * What you can do once the judgments come back: narrow them, read each in
 * three lines, set them against one another, and take the original away.
 *
 * CapabilityGrid names these tools; this section shows them. Each card
 * carries a facsimile of the real control, built from a judgment that is
 * actually in the archive (C.A. 23-P of 2017 and its neighbours), so the page
 * promises nothing the workspace does not already do.
 */

/** A labelled facsimile frame, matching the one in CapabilityGrid. */
const Facsimile = ({ children }) => (
  <div
    aria-hidden="true"
    className="mt-7 overflow-hidden rounded-3xl border border-ash-200 bg-ash-50"
  >
    {children}
  </div>
);

const FilterFacsimile = () => (
  <Facsimile>
    <div className="flex items-center gap-2 border-b border-ash-200 bg-white px-5 py-3">
      <span className="material-symbols-outlined text-[16px] text-brand-500">filter_list</span>
      <span className="font-ui text-[12.5px] font-bold text-ash-800">Filter results</span>
      <span className="ml-auto rounded-full bg-brand-500 px-2 py-0.5 font-ui text-[10.5px] font-bold text-white">
        2
      </span>
    </div>
    <dl className="divide-y divide-ash-200">
      {[
        ['Final decision', 'Dismissed'],
        ['Decided between', '01.01.2016 → 31.12.2024'],
        ['Case or party', 'any'],
        ['Judge', 'Munib Akhtar'],
      ].map(([label, value]) => (
        <div key={label} className="flex items-center justify-between gap-4 px-5 py-2.5">
          <dt className="font-ui text-[11px] font-bold uppercase tracking-wider text-ash-500">
            {label}
          </dt>
          <dd
            className={`truncate font-prose text-[12.5px] ${
              value === 'any' ? 'text-ash-400' : 'font-semibold text-ash-800'
            }`}
          >
            {value}
          </dd>
        </div>
      ))}
    </dl>
    <p className="border-t border-ash-200 bg-white px-5 py-2.5 font-prose text-[12px] text-ash-500">
      Showing <span className="font-bold text-ash-800">2</span> of 5 judgments
    </p>
  </Facsimile>
);

const SummaryFacsimile = () => (
  <Facsimile>
    <p className="border-b border-ash-200 bg-white px-5 py-3 font-display text-[13px] font-bold text-ash-800">
      C.A. 23-P of 2017
    </p>
    <ul className="flex flex-col gap-2.5 px-5 py-4">
      {[
        ['Parties', 'Pirzada Noor-ul-Basar v. Mst. Pakistan Bibi and others'],
        ['Legal problem', 'Property and title: land transferred as dower, absent from the revenue record.'],
        ['Decision', 'Dismissed. The dower deed in the Nikah Nama carried a presumption of correctness.'],
      ].map(([label, text]) => (
        <li key={label} className="flex gap-3">
          <span className="w-[74px] shrink-0 pt-[2px] font-ui text-[9.5px] font-bold uppercase tracking-wider text-brand-600">
            {label}
          </span>
          <span className="flex-1 font-prose text-[12.5px] leading-[1.6] text-ash-700">{text}</span>
        </li>
      ))}
    </ul>
  </Facsimile>
);

const CompareFacsimile = () => (
  <Facsimile>
    <table className="w-full table-fixed border-collapse">
      <thead>
        <tr className="bg-white">
          <th className="w-[30%] border-b border-ash-200 px-4 py-2.5 text-left font-ui text-[10px] font-bold uppercase tracking-wider text-ash-500">
            Field
          </th>
          {['C.A. 23-P/2017', 'C.A. 43-Q/2018'].map((ref) => (
            <th
              key={ref}
              className="border-b border-l border-ash-200 px-4 py-2.5 text-left font-display text-[11.5px] font-bold text-ash-800"
            >
              {ref}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {[
          ['Final decision', 'Dismissed', 'Dismissed'],
          ['Subject', 'Property and title', 'Land and revenue'],
          ['Decided', '29.03.2023', '24.01.2024'],
        ].map(([field, a, b]) => (
          <tr key={field} className="odd:bg-white">
            <td className="border-b border-ash-200 px-4 py-2.5 font-ui text-[11px] font-semibold text-ash-600">
              {field}
            </td>
            <td className="border-b border-l border-ash-200 px-4 py-2.5 font-prose text-[12px] text-ash-800">
              {a}
            </td>
            <td className="border-b border-l border-ash-200 px-4 py-2.5 font-prose text-[12px] text-ash-800">
              {b}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </Facsimile>
);

const DownloadFacsimile = () => (
  <Facsimile>
    <div className="flex items-center gap-3 border-b border-ash-200 bg-white px-5 py-3.5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
        <span className="material-symbols-outlined text-[18px]">picture_as_pdf</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-display text-[12.5px] font-bold text-ash-800">
          judgement_C_A_23-P_2017.pdf
        </span>
        <span className="block font-prose text-[11px] text-ash-500">
          The original, as reported
        </span>
      </span>
    </div>
    <div className="flex flex-wrap gap-2 px-5 py-4">
      <span className="grad-btn inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 font-ui text-[11.5px] font-bold text-white shadow-glow">
        <span className="material-symbols-outlined text-[14px]">download</span>
        Download PDF
      </span>
      <span className="inline-flex items-center gap-1.5 rounded-full border border-ash-300 bg-white px-3.5 py-1.5 font-ui text-[11.5px] font-semibold text-ash-700">
        <span className="material-symbols-outlined text-[14px]">content_copy</span>
        Copy
      </span>
    </div>
  </Facsimile>
);

const TOOLS = [
  {
    icon: 'filter_list',
    title: 'Narrow a long list to the ones that count',
    body: 'When a question returns several authorities, filter them by final decision, by the dates they were decided between, by case number or party, or by the judge on the bench. Every field is optional, and they combine.',
    Figure: FilterFacsimile,
  },
  {
    icon: 'summarize',
    title: 'Read any judgment in three lines',
    body: 'Who the parties were, what the legal problem was, and how it ended — for a single result or for every one of them. Drawn from the indexed record, so it opens at once and says nothing the judgment does not.',
    Figure: SummaryFacsimile,
  },
  {
    icon: 'compare_arrows',
    title: 'Set authorities against one another',
    body: 'Put the retrieved judgments in one table — disposition, subject, parties, date — and see at a glance where two lines of authority agree on a question and where they part.',
    Figure: CompareFacsimile,
  },
  {
    icon: 'download',
    title: 'Take the original away with you',
    body: 'Download the reported judgment as it was handed down, or copy the analysis as plain text with its case number and a line reminding the reader to verify it against the original.',
    Figure: DownloadFacsimile,
  },
];

const ResultToolkit = () => {
  return (
    <section
      aria-labelledby="toolkit-title"
      className="w-full px-5 py-20 sm:px-8 md:py-28"
    >
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="When the results come back"
          icon="fact_check"
          title={<span id="toolkit-title">The authorities arrive. Now</span>}
          accent="do something with them"
          lede="Retrieval is the beginning of the work, not the end of it. Everything below acts on the judgments already on your screen — no second search, no waiting."
          className="mx-auto"
        />

        <ul className="mt-14 grid grid-cols-1 gap-5 md:mt-20 lg:grid-cols-2">
          {TOOLS.map(({ icon, title, body, Figure }, index) => (
            <Reveal
              as="li"
              key={title}
              variant="tilt"
              delay={index * 110}
              className="lift-card group flex flex-col rounded-4xl border border-ash-200 bg-white p-8 shadow-card hover:border-brand-200 hover:shadow-card-lg sm:p-9"
            >
              <span
                aria-hidden="true"
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
              >
                <span className="material-symbols-outlined text-[22px]">{icon}</span>
              </span>

              <h3 className="mt-6 font-display text-[clamp(1.25rem,2.1vw,1.5rem)] font-bold leading-[1.2] tracking-[-0.02em] text-ash-900">
                {title}
              </h3>

              <p className="mt-3.5 font-prose text-[14.5px] leading-[1.72] text-ash-600">{body}</p>

              <div className="mt-auto">
                <Figure />
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
};

export default ResultToolkit;
