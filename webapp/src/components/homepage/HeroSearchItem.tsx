import { Command } from 'cmdk'
import type { CatalogHit, Severity } from '@/lib/catalog-search'

interface Props {
  hit: CatalogHit
  onSelect: (slug: string) => void
  id: string
}

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
  info: 'info',
}

/**
 * Single dropdown row. Severity-tinted score pill on the right.
 * cmdk owns selected state via the `data-selected` attribute on the
 * underlying div — we style off that.
 */
export default function HeroSearchItem({ hit, onSelect, id }: Props) {
  return (
    <Command.Item
      id={id}
      value={`${hit.kind}:${hit.slug}`}
      onSelect={() => onSelect(hit.slug)}
      className="p1-dropdown-item"
    >
      <span className="p1-dropdown-name">{hit.display_name}</span>
      <span className="p1-dropdown-editor">{hit.editor}</span>
      <span className={`p1-dropdown-meta sev-${hit.severity}`}>
        <span className="sev-label">{SEVERITY_LABEL[hit.severity]}</span>
        <span className="sev-score">{hit.scan_score}</span>
      </span>
    </Command.Item>
  )
}
