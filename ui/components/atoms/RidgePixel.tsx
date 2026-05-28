/**
 * Dark-slate divider with the orange tick-ruler accent + pixel teeth — 96px tall.
 *
 * Layered SVG ported verbatim from the hi-fi mockup: dashed alignment line,
 * orange registration-dot clusters at each corner, paper-color rising teeth,
 * paper bottom slab, and a scatter of ink+orange poking squares at the boundary.
 * Used as the transition INTO dark sections (install band → feeds, CTA, footer).
 * `aria-hidden` because it's purely decorative.
 */
export default function RidgePixel({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-pixel ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
      <svg
        viewBox="0 0 1280 96"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <line x1="0" y1="30" x2="1280" y2="30" stroke="#F8FAFC" strokeOpacity="0.22" strokeDasharray="5 7" />
        <g fill="#F97316">
          <circle cx="22" cy="24" r="3" />
          <circle cx="36" cy="24" r="3" />
          <circle cx="50" cy="24" r="3" />
          <circle cx="1230" cy="24" r="3" />
          <circle cx="1244" cy="24" r="3" />
          <circle cx="1258" cy="24" r="3" />
        </g>
        <g fill="#F8FAFC">
          <rect x="40" y="52" width="6" height="6" />
          <rect x="78" y="48" width="6" height="10" />
          <rect x="112" y="54" width="6" height="4" />
          <rect x="160" y="46" width="6" height="12" />
          <rect x="208" y="52" width="6" height="6" />
          <rect x="252" y="50" width="6" height="8" />
          <rect x="296" y="44" width="6" height="14" />
          <rect x="344" y="52" width="6" height="6" />
          <rect x="390" y="48" width="6" height="10" />
          <rect x="436" y="54" width="6" height="4" />
          <rect x="484" y="46" width="6" height="12" />
          <rect x="530" y="52" width="6" height="6" />
          <rect x="720" y="48" width="6" height="10" />
          <rect x="768" y="54" width="6" height="4" />
          <rect x="816" y="46" width="6" height="12" />
          <rect x="864" y="52" width="6" height="6" />
          <rect x="912" y="50" width="6" height="8" />
          <rect x="960" y="44" width="6" height="14" />
          <rect x="1008" y="52" width="6" height="6" />
          <rect x="1056" y="48" width="6" height="10" />
          <rect x="1104" y="54" width="6" height="4" />
          <rect x="1152" y="46" width="6" height="12" />
          <rect x="1200" y="52" width="6" height="6" />
          <rect x="1244" y="50" width="6" height="8" />
        </g>
        <rect x="0" y="58" width="1280" height="38" fill="#F8FAFC" />
        <g fill="#0F172A">
          <rect x="58" y="58" width="6" height="6" />
          <rect x="180" y="58" width="6" height="4" />
          <rect x="320" y="58" width="6" height="8" />
          <rect x="468" y="58" width="6" height="6" />
          <rect x="610" y="58" width="6" height="4" />
          <rect x="752" y="58" width="6" height="8" />
          <rect x="894" y="58" width="6" height="6" />
          <rect x="1042" y="58" width="6" height="4" />
          <rect x="1186" y="58" width="6" height="8" />
        </g>
        <g fill="#F97316">
          <rect x="240" y="58" width="6" height="6" />
          <rect x="540" y="58" width="6" height="4" />
          <rect x="840" y="58" width="6" height="6" />
          <rect x="1140" y="58" width="6" height="4" />
        </g>
        <line x1="0" y1="82" x2="1280" y2="82" stroke="#0F172A" strokeOpacity="0.18" strokeDasharray="3 5" />
      </svg>
    </div>
  )
}
