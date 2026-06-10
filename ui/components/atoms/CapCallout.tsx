export type CapCalloutBand = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

/**
 * The cap-reason callout under the score hero — explains why the grade is what it
 * is (e.g. "Capped to Red — 1 critical finding…" or "No cap applied…"). Band tint
 * is inherited from the enclosing `.score-cell.{g|y|o|r}` (I-5.6 design §6/§9). A
 * green band shows a check glyph; any risk band shows a warning glyph.
 */
export default function CapCallout({
  band,
  text,
  className = '',
}: {
  band: CapCalloutBand
  text: string
  className?: string
}) {
  const clean = band === 'green'
  return (
    <div className={`cap-reason ${className}`.trim()}>
      <svg
        className="cr-ic"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden="true"
      >
        {clean ? (
          <path d="M20 6 9 17l-5-5" />
        ) : (
          <>
            <path d="M12 3 2 20h20L12 3Z" />
            <path d="M12 10v4" />
            <path d="M12 17.5v.5" />
          </>
        )}
      </svg>
      <p>{text}</p>
    </div>
  )
}
