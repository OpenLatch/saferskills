interface Props {
  min: number
  max: number
  onChange: (min: number, max: number) => void
}

/**
 * Accessible dual-thumb score-range slider. Two overlaid native range inputs
 * (keyboard + screen-reader friendly) drive `score_min` / `score_max`; a teal
 * fill segment + grid-lined track render the mockup's `.slider-stub` look.
 * The thumbs keep a 1-point gap so they never cross.
 */
export default function ScoreRangeSlider({ min, max, onChange }: Props) {
  const left = `${min}%`
  const width = `${Math.max(0, max - min)}%`

  function handleMin(value: number) {
    onChange(Math.min(value, max - 1), max)
  }
  function handleMax(value: number) {
    onChange(min, Math.max(value, min + 1))
  }

  return (
    <div className="grp">
      <h6>Score range</h6>
      <div className="score-slider">
        <div className="track" aria-hidden="true" />
        <div className="fill" style={{ left, width }} aria-hidden="true" />
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={min}
          aria-label="Minimum score"
          onChange={(e) => handleMin(Number.parseInt(e.target.value, 10))}
        />
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={max}
          aria-label="Maximum score"
          onChange={(e) => handleMax(Number.parseInt(e.target.value, 10))}
        />
      </div>
      <div className="slider-cap">
        <span>
          <b>{min}</b> min
        </span>
        <span>
          <b>{max}</b> max
        </span>
      </div>
    </div>
  )
}
