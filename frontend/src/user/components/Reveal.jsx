import { cloneElement, isValidElement, useEffect, useRef, useState } from 'react';

/**
 * Viewport-triggered reveal wrapper.
 *
 * IntersectionObserver + CSS classes (see index.css), so no animation library
 * is shipped and only opacity, transform and filter animate — all of which
 * the compositor handles without touching layout.
 *
 * variant: 'up' (default) | 'rise' | 'scale' | 'tilt' | 'mask' | 'left' |
 *          'right' | 'fade'
 * delay:   ms before this element starts
 * stagger: ms between direct children, so a grid cascades
 *
 * Reveals once, then stops observing. Reduced motion is handled in CSS.
 */
const Reveal = ({
  as: Tag = 'div',
  variant = 'up',
  delay = 0,
  threshold = 0.15,
  stagger = 0,
  className = '',
  style,
  children,
  ...rest
}) => {
  const ref = useRef(null);
  // When IntersectionObserver is unavailable, start visible so content is
  // never withheld — no state update needed on mount.
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined');

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold, rootMargin: '0px 0px -8% 0px' }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold]);

  // `stagger` cascades the direct children instead of revealing the block as
  // one slab: each child is handed its index, and the CSS turns that into a
  // delay. A grid then arrives card by card, which is the difference between
  // "it animated" and "it was choreographed".
  const staggered =
    stagger && Array.isArray(children)
      ? children.map((child, i) =>
          isValidElement(child)
            ? cloneElement(child, {
                style: { ...(child.props.style || {}), '--i': i },
              })
            : child
        )
      : children;

  return (
    <Tag
      ref={ref}
      data-reveal={variant}
      className={`reveal ${stagger ? 'reveal-group' : ''} ${visible ? 'is-visible' : ''} ${className}`
        .replace(/\s+/g, ' ')
        .trim()}
      style={{
        ...style,
        ...(delay ? { '--reveal-delay': `${delay}ms` } : null),
        ...(typeof stagger === 'number' ? { '--stagger': `${stagger}ms` } : null),
      }}
      {...rest}
    >
      {staggered}
    </Tag>
  );
};

export default Reveal;
