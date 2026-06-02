interface Props {
  /** Current lower value. */
  min: number
  /** Current upper value. */
  max: number
  /** Fired with the next `(min, max)` pair; thumbs never cross (kept `step` apart). */
  onChange: (min: number, max: number) => void
  /** Scale lower bound. Default 0. */
  rangeMin?: number
  /** Scale upper bound. Default 100. */
  rangeMax?: number
  /** Step + minimum gap between thumbs. Default 1. */
  step?: number
  /** Accessible name for the lower thumb. */
  minAriaLabel?: string
  /** Accessible name for the upper thumb. */
  maxAriaLabel?: string
  /** Trailing word after the lower value in the caption. Default `min`. */
  minCapLabel?: string
  /** Trailing word after the upper value in the caption. Default `max`. */
  maxCapLabel?: string
  /** Optional accessible group label wrapping both thumbs + caption. */
  label?: string
}

/**
 * Accessible dual-thumb range slider. Two overlaid native range inputs
 * (keyboard + screen-reader friendly) drive the lower/upper bound; a teal fill
 * segment + grid-lined track render the brand look. The thumbs keep a `step`
 * gap so they never cross.
 *
 * Lifted from the catalog `ScoreRangeSlider`; CSS (`.score-slider`/`.slider-cap`)
 * is DS-owned in `ui/styles/components.css`. Callers supply their own heading
 * wrapper (the catalog keeps its `.grp` / `<h6>`).
 */
export default function RangeSlider({
  min,
  max,
  onChange,
  rangeMin = 0,
  rangeMax = 100,
  step = 1,
  minAriaLabel = 'Minimum',
  maxAriaLabel = 'Maximum',
  minCapLabel = 'min',
  maxCapLabel = 'max',
  label,
}: Props) {
  const span = rangeMax - rangeMin || 1
  const left = `${((min - rangeMin) / span) * 100}%`
  const width = `${(Math.max(0, max - min) / span) * 100}%`

  function handleMin(value: number) {
    onChange(Math.min(value, max - step), max)
  }
  function handleMax(value: number) {
    onChange(min, Math.max(value, min + step))
  }

  const body = (
    <>
      <div className="score-slider">
        <div className="track" aria-hidden="true" />
        <div className="fill" style={{ left, width }} aria-hidden="true" />
        <input
          type="range"
          min={rangeMin}
          max={rangeMax}
          step={step}
          value={min}
          aria-label={minAriaLabel}
          onChange={(e) => handleMin(Number.parseInt(e.target.value, 10))}
        />
        <input
          type="range"
          min={rangeMin}
          max={rangeMax}
          step={step}
          value={max}
          aria-label={maxAriaLabel}
          onChange={(e) => handleMax(Number.parseInt(e.target.value, 10))}
        />
      </div>
      <div className="slider-cap">
        <span>
          <b>{min}</b> {minCapLabel}
        </span>
        <span>
          <b>{max}</b> {maxCapLabel}
        </span>
      </div>
    </>
  )

  return label ? (
    <div role="group" aria-label={label}>
      {body}
    </div>
  ) : (
    body
  )
}
