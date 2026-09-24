import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';
import MediaFrame from './MediaFrame';

/**
 * What the archive is made of, shown rather than asserted.
 *
 * Four photographs in an asymmetric mosaic, each captioned with the part of
 * the pipeline it stands for — the shelf that is the corpus, the bench that
 * is the authority, the volume that is the citation, the desk that is the
 * output. The tall shelf leads because it is the only one that conveys
 * quantity, which is the point the section is making.
 *
 * Every panel is a `group`, so the photograph pushes in and the sheen
 * crosses it on hover; the caption sits on the wash, not on bare image.
 */
const PANELS = [
  {
    name: 'stacks',
    span: 'sm:col-span-2 sm:row-span-2',
    ratio: '4 / 5',
    tallRatio: 'auto',
    kicker: 'The corpus',
    title: 'Reported judgments, whole',
    body: 'Not headnotes or digests. The full reported text, extracted page by page, with optical recognition for the scanned volumes.',
    stat: '9 indexed',
  },
  {
    name: 'scales',
    span: '',
    ratio: '4 / 3',
    kicker: 'The authority',
    title: 'Every finding is attributed',
    body: 'A passage arrives with its appeal number, or it does not arrive.',
    stat: 'Cited',
  },
  {
    name: 'volume',
    span: '',
    ratio: '4 / 3',
    kicker: 'The division',
    title: 'Six parts, marked before indexing',
    body: 'Coram, facts, arguments, issues, ratio, order.',
    stat: 'Six',
  },
  {
    name: 'desk',
    span: 'sm:col-span-2',
    ratio: '16 / 9',
    kicker: 'The output',
    title: 'A passage you can put in a brief',
    body: 'Reassembled in reading order, with the disposition attached, and exportable as clean text.',
    stat: 'Export ready',
  },
];

const Panel = ({ panel, index, tall = false }) => (
  <Reveal
    as="li"
    variant="fade"
    delay={index * 110}
    className={`group relative ${panel.span}`}
  >
    <MediaFrame
      name={panel.name}
      ratio={tall ? panel.tallRatio ?? panel.ratio : panel.ratio}
      wash="ink"
      zoom
      className={`ring-photo sheen h-full w-full rounded-4xl shadow-card transition-shadow duration-500 group-hover:shadow-card-lg ${
        tall ? 'min-h-[30rem]' : ''
      }`}
    >
      {/* Standing stat, top-right, on glass. */}
      <span className="absolute right-5 top-5 z-[2] inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/15 px-3 py-1 font-ui text-[11.5px] font-bold text-white backdrop-blur-md">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
        {panel.stat}
      </span>

      <figcaption className="absolute inset-x-0 bottom-0 z-[2] flex flex-col p-6 sm:p-7">
        <span className="font-ui text-[11px] font-bold uppercase tracking-[0.14em] text-brand-200">
          {panel.kicker}
        </span>

        <span
          className={`mt-2.5 font-display font-bold leading-[1.16] tracking-[-0.02em] text-white ${
            tall ? 'text-[clamp(1.375rem,2.4vw,1.75rem)]' : 'text-[17px]'
          }`}
        >
          {panel.title}
        </span>

        {/* The body is held back until hover on the pointer devices that can
            reveal it, and always shown where hover does not exist. */}
        <span
          className={`mt-2.5 max-w-[34ch] font-prose leading-[1.65] text-white/80 ${
            tall ? 'text-[14px]' : 'text-[13px]'
          } transition-all duration-500 md:max-h-0 md:-translate-y-1 md:overflow-hidden md:opacity-0 md:group-hover:max-h-32 md:group-hover:translate-y-0 md:group-hover:opacity-100`}
        >
          {panel.body}
        </span>
      </figcaption>
    </MediaFrame>
  </Reveal>
);

const CorpusMosaic = () => {
  const [lead, ...rest] = PANELS;

  return (
    <section aria-labelledby="corpus-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="Inside the archive"
          icon="auto_stories"
          title={<span id="corpus-title">Bound volumes, taken apart and</span>}
          accent="put back in order"
          lede="A law report is a physical object with a structure. The archive keeps that structure — it only changes what you have to do to reach the part you need."
          className="mx-auto"
        />

        <ul className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 md:mt-20 lg:grid-cols-4">
          <Panel panel={lead} index={0} tall />
          {rest.map((panel, index) => (
            <Panel key={panel.name} panel={panel} index={index + 1} />
          ))}
        </ul>
      </div>
    </section>
  );
};

export default CorpusMosaic;
