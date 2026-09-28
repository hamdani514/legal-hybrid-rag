import { Link } from 'react-router-dom';
import MediaFrame from './MediaFrame';

/**
 * The left-hand panel of every authentication screen.
 *
 * This is deliberately identical on sign in, sign up, OTP, password recovery
 * and password reset — the same gradient, the same scales, the same three
 * points. A panel that changed between steps would make the recovery flow
 * feel like five unrelated pages instead of one journey.
 *
 * Inlined rather than loaded from /assets/legal/scales.svg because the source
 * file strokes with `currentColor`, which an <img> cannot inherit.
 */
const ADMIN_POINTS = [
  {
    icon: 'cloud_upload',
    title: 'Ingest and classify',
    body: 'Upload reported judgments and watch each one divided into its six parts.',
  },
  {
    icon: 'monitor_heart',
    title: 'Watch the pipeline',
    body: 'Extraction, parsing and embedding status for every document in the archive.',
  },
  {
    icon: 'admin_panel_settings',
    title: 'Manage access',
    body: 'Accounts, support queries and administrator credentials in one console.',
  },
];

const POINTS = [
  {
    icon: 'travel_explore',
    title: 'Ask in plain language',
    body: 'Put the legal question the way you would to a colleague.',
  },
  {
    icon: 'format_quote',
    title: 'Read the Court’s own words',
    body: 'Every answer names the judgment and its appeal number.',
  },
  {
    icon: 'lock',
    title: 'Your research stays private',
    body: 'Queries are never used to train the underlying model.',
  },
];

const ScalesMark = ({ className = '' }) => (
  <svg
    viewBox="0 0 200 200"
    fill="none"
    stroke="currentColor"
    strokeWidth="3"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    className={className}
  >
    <path d="M100 26v138" />
    <circle cx="100" cy="20" r="7" fill="currentColor" stroke="none" />
    <path d="M30 52h140" />
    <path d="M30 52 8 106h44z" />
    <path d="M170 52l22 54h-44z" />
    <path d="M8 106a22 22 0 0 0 44 0" />
    <path d="M148 106a22 22 0 0 0 44 0" />
    <path d="M30 52v10M170 52v10" />
    <path d="M70 164h60" />
    <path d="M60 178h80" />
    <path d="M70 164l-10 14M130 164l10 14" />
  </svg>
);

const COPY = {
  user: {
    media: 'stacks',
    badge: 'Supreme Court of Pakistan',
    badgeIcon: 'balance',
    lead: 'Legal research that finds the',
    accent: 'reasoning',
    body:
      'Every judgment is split into its facts, arguments, issues, ratio and order before it is indexed — so you get the passage that decides your point.',
    points: POINTS,
  },
  admin: {
    media: 'desk',
    badge: 'Administration',
    badgeIcon: 'shield_person',
    lead: 'The console behind the',
    accent: 'archive',
    body:
      'Ingest judgments, follow every stage of the pipeline, and manage the accounts that research against it.',
    points: ADMIN_POINTS,
  },
};

const AuthVisual = ({ variant = 'user' }) => {
  const copy = COPY[variant] ?? COPY.user;
  return (
    <aside
      aria-label="About Verdict AI"
      className="relative hidden overflow-hidden bg-slate-950 lg:flex lg:flex-col lg:justify-between"
    >
      {/* The authentic photograph with natural warmth — no blue wash */}
      <MediaFrame
        name={copy.media}
        wash="none"
        drift
        ratio="auto"
        className="absolute inset-0 h-full w-full object-cover"
        aria-hidden="true"
      />

      {/* Neutral dark vignette overlay to preserve natural library wood and paper tones */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/92 via-black/65 to-black/35"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent"
      />
      <span aria-hidden="true" className="media-rule pointer-events-none absolute inset-0 opacity-35" />

      {/* Subtle neutral bloom and watermark scales */}
      <span
        aria-hidden="true"
        className="float-y-slow pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-white/5 blur-3xl"
      />
      <ScalesMark className="pointer-events-none absolute -right-16 bottom-16 h-[26rem] w-[26rem] text-white/[0.07]" />

      {/* ── Claim ──────────────────────────────────────────────────── */}
      <div className="relative z-10 px-12 pt-12 xl:px-14">
        {/* Clickable Brand Wordmark to return Home */}
        <Link
          to="/"
          className="group mb-8 inline-flex items-center gap-2.5 transition-transform duration-200 hover:scale-[1.02]"
          aria-label="Verdict AI Home"
        >
          <span
            aria-hidden="true"
            className="grad-brand flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-glow transition-transform duration-200 group-hover:scale-105"
          >
            <span className="material-symbols-outlined text-[21px]">balance</span>
          </span>
          <span className="font-display text-[20px] font-bold tracking-[-0.02em] text-white">
            Verdict<span className="text-cyan-300">AI</span>
          </span>
        </Link>

        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-black/40 px-4 py-1.5 font-ui text-[12px] font-semibold text-white backdrop-blur-md shadow-sm">
            <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
              {copy.badgeIcon}
            </span>
            {copy.badge}
          </span>
        </div>

        <h2 className="mt-8 max-w-[20ch] font-display text-[clamp(2rem,2.6vw,2.75rem)] font-bold leading-[1.08] tracking-[-0.03em] text-white">
          {copy.lead} <span className="text-amber-200/90">{copy.accent}</span>
        </h2>

        <p className="mt-5 max-w-[34ch] font-prose text-[15px] leading-[1.72] text-white/85">
          {copy.body}
        </p>
      </div>

      {/* ── The three points ───────────────────────────────────────── */}
      <ul className="relative z-10 flex flex-col gap-5 px-12 py-10 xl:px-14">
        {copy.points.map(({ icon, title, body }) => (
          <li key={title} className="flex items-start gap-4">
            <span
              aria-hidden="true"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-white/15 bg-black/40 text-white backdrop-blur-md shadow-sm"
            >
              <span className="material-symbols-outlined text-[19px]">{icon}</span>
            </span>
            <span className="flex flex-col">
              <span className="font-display text-[14px] font-bold text-white">{title}</span>
              <span className="mt-1 font-prose text-[13px] leading-5 text-white/70">{body}</span>
            </span>
          </li>
        ))}
      </ul>

      {/* ── A real retrieved result ────────────────────────────────── */}
      <div className="relative z-10 px-12 pb-14 xl:px-14" aria-hidden="true">
        <div className="rounded-3xl border border-white/15 bg-black/50 p-5 backdrop-blur-md shadow-2xl">
          <div className="flex items-center justify-between gap-3">
            <span className="font-display text-[12.5px] font-semibold text-white">
              Civil Appeal No. 23-P of 2017
            </span>
            <span className="rounded-full bg-white px-2.5 py-0.5 font-ui text-[11px] font-bold text-slate-900 shadow-sm">
              0.69
            </span>
          </div>

          <p className="mt-3 font-prose text-[12.5px] leading-[1.65] text-white/85">
            The dispute concerned wrong entries in the revenue record, which{' '}
            <span className="text-amber-200 font-semibold">in no way can be termed as a matter relating to dower</span>
            .
          </p>

          <span className="mt-3.5 inline-flex items-center gap-1.5 rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2.5 py-1 font-ui text-[10.5px] font-bold text-emerald-300">
            <span aria-hidden="true" className="material-symbols-outlined text-[13px]">
              check_circle
            </span>
            Appeal dismissed
          </span>
        </div>
      </div>
    </aside>
  );
};

export default AuthVisual;
