import type { ReactNode } from 'react'

interface Props {
  /** Checked state (controlled). */
  checked: boolean
  /** Fired with the next checked value on click / Space / Enter. */
  onChange: (checked: boolean) => void
  /** Visible label. Provides the accessible name when it is plain text. */
  label: ReactNode
  /** Glyph shape: a square check (default) or a round radio dot. Single-select
   *  groups use `radio` for the familiar round affordance — the control is still
   *  a checkbox semantically (no enclosing radiogroup). */
  variant?: 'check' | 'radio'
  /** Optional trailing count, right-aligned (e.g. a facet result count). */
  count?: number
  /** Optional node rendered between the box and the label (e.g. a color swatch). */
  adornment?: ReactNode
  /** Full-width row with vertical padding — the filter-sidebar layout. */
  block?: boolean
  /** Accessible name override — only needed when `label` is not plain text. */
  ariaLabel?: string
  className?: string
}

/**
 * DS checkbox / radio control.
 *
 * Token-driven and **dark-correct by construction**: the box border reads
 * `--color-ink` and the checked fill `--brand-primary`, both of which flip with
 * the theme — so there is no `html.dark` override to lose a specificity race
 * (the failure mode that left the old hand-rolled catalog checkbox invisible in
 * dark mode). One source of truth in `ui/styles/components.css` (`.ds-check*`).
 *
 * Rendered as a `<button role="checkbox">` (toggles on click / Space / Enter),
 * so it works for filter facets (multi-select) and standalone form checkboxes.
 */
export default function Checkbox({
  checked,
  onChange,
  label,
  variant = 'check',
  count,
  adornment,
  block,
  ariaLabel,
  className,
}: Props) {
  const cls = [
    'ds-check',
    variant === 'radio' && 'ds-check--radio',
    block && 'ds-check--block',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={ariaLabel}
      data-on={checked}
      className={cls}
      onClick={() => onChange(!checked)}
    >
      <span className="ds-check-box" aria-hidden="true" />
      {adornment}
      <span className="ds-check-label">{label}</span>
      {count != null && <span className="ds-check-count">{count.toLocaleString()}</span>}
    </button>
  )
}
