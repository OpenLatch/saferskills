import { Command } from 'cmdk'

export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export interface SearchHit {
  kind: string
  slug: string
  display_name: string
  editor: string
  scan_score: number
  severity: Severity
}

interface Props {
  hit: SearchHit
  onSelect: (hit: SearchHit) => void
  id: string
}

/**
 * Single dropdown row — `display_name` · `editor` · severity-tinted score pill.
 * cmdk drives the selected-state via `data-selected` on the underlying div;
 * the row styles in `ui/styles/components.css` key off that attribute.
 */
export default function SearchDropdownItem({ hit, onSelect, id }: Props) {
  return (
    <Command.Item
      id={id}
      value={`${hit.kind}:${hit.slug}`}
      onSelect={() => onSelect(hit)}
      className="search-dropdown-item"
    >
      <span className="search-dropdown-name">{hit.display_name}</span>
      <span className="search-dropdown-editor">{hit.editor}</span>
      <span className={`search-dropdown-meta sev-${hit.severity}`}>
        <span className="sev-label">{hit.severity}</span>
        <span className="sev-score">{hit.scan_score}</span>
      </span>
    </Command.Item>
  )
}
