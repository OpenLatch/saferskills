import { useId } from 'react'

interface ToggleProps {
  checked: boolean
  onChange: (next: boolean) => void
  /** Visible label, e.g. "Make results public". */
  label: string
  /** Links a helper line to the switch for SR users (aria-describedby). */
  describedById?: string
  disabled?: boolean
  /** Track colour when ON. `teal` = public default; `orange` = URL/repo mode. */
  tone?: 'teal' | 'orange'
  /** Smaller track (homepage audit panel). */
  compact?: boolean
}

/**
 * Self-contained accessible switch (`role="switch"`) — no Radix dependency.
 * Space/Enter toggle via the native button; the thumb slides on `transform`
 * (reduced-motion → instant). Teal track when ON, orange in URL/repo mode.
 */
export default function Toggle({
  checked,
  onChange,
  label,
  describedById,
  disabled,
  tone = 'teal',
  compact,
}: ToggleProps) {
  const labelId = useId()
  return (
    <span className={`toggle-field${compact ? ' toggle-field--compact' : ''}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={describedById}
        data-tone={tone}
        disabled={disabled}
        className={`toggle${compact ? ' toggle--compact' : ''}`}
        onClick={() => onChange(!checked)}
      >
        <span className="toggle-thumb" />
      </button>
      <span className="toggle-label" id={labelId}>
        {label}
      </span>
    </span>
  )
}
