/**
 * The filter icon, from public/assets/filter.svg.
 *
 * Used as a CSS mask rather than an <img>: the file's fill is fixed black,
 * while a mask takes its shape from the file and its colour from the text
 * around it, so it follows hover, active and locked states like the
 * icon-font icons beside it.
 */
const FilterIcon = ({ size = 16, className = '' }) => {
  const mask = 'url(/assets/filter.svg) center / contain no-repeat';
  return (
    <span
      aria-hidden="true"
      className={`inline-block flex-shrink-0 bg-current ${className}`}
      style={{ width: size, height: size, WebkitMask: mask, mask }}
    />
  );
};

export default FilterIcon;
