import { useState } from 'react';
import { MEDIA } from '../../media';

/**
 * The one way a photograph enters the page.
 *
 * Everything the site's photographs need in common lives here: the reserved
 * box (so nothing reflows when the bytes arrive), the ink wash that pulls a
 * warm brown-and-brass photograph into a blue-and-violet brand, the slow
 * settle as it decodes, and the crop that holds the right part of the frame.
 *
 * Props
 *  name     key into MEDIA, or pass `media` directly
 *  ratio    CSS aspect-ratio for the frame; defaults to the file's own.
 *           Pass `false` to set none, and let a class carry a responsive one
 *  wash     'none' | 'soft' | 'ink' | 'brand' | 'base' — how heavily the
 *           photograph is tinted. Use 'ink' or 'brand' under white text.
 *  zoom     slow scale on hover of the nearest `.group` ancestor
 *  drift    continuous Ken Burns drift, for standing hero bands
 *  eager    skip lazy loading — only for anything above the fold
 *  grain    lay the statute hairline pattern over the wash
 */
const WASHES = {
  none: null,
  soft: 'bg-gradient-to-t from-ash-900/35 via-ash-900/5 to-transparent',
  ink: 'bg-gradient-to-t from-ash-900/85 via-ash-900/45 to-ash-900/15',
  // Weighted, not flat: near-opaque ink under the copy on the left, easing
  // to a blue-violet tint on the right where the photograph is the subject.
  brand:
    'bg-[linear-gradient(104deg,rgba(9,20,38,0.92)_0%,rgba(11,25,48,0.78)_34%,rgba(0,80,204,0.44)_66%,rgba(36,0,255,0.46)_100%)]',
  base: 'bg-[linear-gradient(180deg,rgba(13,28,50,0.06)_0%,rgba(13,28,50,0.42)_100%)]',
  // Dark at the reading edge, clear at the far one — for a band whose copy
  // is pinned left over a photograph that is bright on that side.
  edge:
    'bg-[linear-gradient(100deg,rgba(9,20,38,0.93)_0%,rgba(9,20,38,0.84)_34%,rgba(9,20,38,0.44)_68%,rgba(9,20,38,0.18)_100%)]',
};

const MediaFrame = ({
  name,
  media,
  ratio,
  wash = 'soft',
  zoom = false,
  drift = false,
  eager = false,
  grain = false,
  className = '',
  imgClassName = '',
  children,
  ...rest
}) => {
  const item = media ?? MEDIA[name];
  const [loaded, setLoaded] = useState(false);

  if (!item) return null;

  const washClass = WASHES[wash] ?? WASHES.soft;

  // Tailwind emits every `position` utility in one group, and `relative`
  // comes after `absolute` in that group. Writing both on the same element
  // therefore resolves to `relative` whatever the order in the attribute, so
  // the default is withheld whenever the caller positions the frame itself.
  const positioned = /(?:^|\s)(?:absolute|fixed|sticky)(?:\s|$)/.test(className);

  return (
    <figure
      className={`media-frame ${positioned ? '' : 'relative'} overflow-hidden ${className}`
        .replace(/\s+/g, ' ')
        .trim()}
      style={ratio === false ? undefined : { aspectRatio: ratio ?? `${item.w} / ${item.h}` }}
      {...rest}
    >
      <img
        src={item.src}
        alt={item.alt}
        width={item.w}
        height={item.h}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        fetchPriority={eager ? 'high' : 'auto'}
        onLoad={() => setLoaded(true)}
        style={{ objectPosition: item.focus }}
        className={`absolute inset-0 h-full w-full object-cover ${
          loaded ? 'media-img--in' : 'media-img--out'
        } ${zoom ? 'media-zoom' : ''} ${drift ? 'media-drift' : ''} ${imgClassName}`.trim()}
      />

      {washClass && (
        <span aria-hidden="true" className={`pointer-events-none absolute inset-0 ${washClass}`} />
      )}

      {grain && <span aria-hidden="true" className="media-rule pointer-events-none absolute inset-0" />}

      {/* Anything laid over the photograph — captions, badges, stats. */}
      {children}
    </figure>
  );
};

export default MediaFrame;
