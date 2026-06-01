/**
 * Discrete tick-ruler divider — the quietest member of the ridge family. A
 * theme-aware tick ruler (orange majors + faint minors) centered on a slim
 * paper-deep band; no fill, no hatch, so the transition stays focused on the
 * rules. Reads light-on-light and dark-on-dark, both subtle (the band + tick
 * colors are token-driven, so it themes for free). `aria-hidden` because it is
 * purely decorative.
 */
export default function RidgeRuler({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-ruler ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
    </div>
  )
}
