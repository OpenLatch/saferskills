function humanize(label: string): string {
  return label.charAt(0).toUpperCase() + label.slice(1)
}

/**
 * The trust-tier pill in the score hero — e.g. `Cloud-validated · Client-administered`
 * — with a focus/hover honesty tooltip. Keyboard-focusable
 * (`tabIndex=0`) and wired to its tooltip via `aria-describedby`; the tooltip
 * dismisses on blur/Escape via native focus handling. `labels` are the trust-TIER
 * labels only (the wider trust_labels enum renders as provenance chips).
 */
export default function TrustTierPill({
  labels,
  tooltip = 'The agent ran these tests on its own machine; SaferSkills graded the raw results',
  tipId = 'trust-tip',
  className = '',
}: {
  labels: string[]
  tooltip?: string
  tipId?: string
  className?: string
}) {
  const text = labels.map(humanize).join(' · ')
  return (
    <span className={`trust-pill ${className}`.trim()} tabIndex={0} aria-describedby={tipId}>
      {text}
      <span className="ti" aria-hidden="true">
        i
      </span>
      <span className="tip" id={tipId} role="tooltip">
        {tooltip}
      </span>
    </span>
  )
}
