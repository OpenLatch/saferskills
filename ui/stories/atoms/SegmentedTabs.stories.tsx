import type { Story } from '@ladle/react'
import { useState } from 'react'
import SegmentedTabs, { panelId } from '../../components/atoms/SegmentedTabs'

const SCAN_TABS = [
  { id: 'upload', label: 'Upload', accent: 'teal' as const },
  { id: 'url', label: 'Scan repo', accent: 'orange' as const },
]

export const SegmentedTwoTab: Story = () => {
  const [v, setV] = useState('upload')
  return (
    <div style={{ maxWidth: 420 }}>
      <SegmentedTabs
        ariaLabel="Scan mode"
        idBase="scan"
        tabs={SCAN_TABS}
        value={v}
        onChange={setV}
      />
      <div id={panelId('scan', v)} role="tabpanel" aria-labelledby={`scan-tab-${v}`} style={{ padding: 16 }}>
        {v === 'upload' ? 'Upload pane (teal accent)' : 'Scan-repo pane (orange accent)'}
      </div>
    </div>
  )
}

export const UnderlineWithCounts: Story = () => {
  const [v, setV] = useState('score')
  const tabs = [
    { id: 'score', label: 'Score breakdown', count: 7 },
    { id: 'versions', label: 'Version history', count: 3 },
    { id: 'source', label: 'Source' },
  ]
  return (
    <div style={{ maxWidth: 560 }}>
      <SegmentedTabs
        variant="underline"
        ariaLabel="Report sections"
        idBase="rep"
        tabs={tabs}
        value={v}
        onChange={setV}
      />
      <div id={panelId('rep', v)} role="tabpanel" aria-labelledby={`rep-tab-${v}`} style={{ padding: 16 }}>
        Panel: {v}
      </div>
    </div>
  )
}

export const KeyboardNav: Story = () => {
  const [v, setV] = useState('upload')
  return (
    <div style={{ maxWidth: 420 }}>
      <p style={{ fontFamily: 'monospace', fontSize: 12, marginBottom: 8 }}>
        Focus a tab, then ←/→ to move, Enter/Space to activate.
      </p>
      <SegmentedTabs ariaLabel="Scan mode" idBase="kb" tabs={SCAN_TABS} value={v} onChange={setV} />
      <div id={panelId('kb', v)} role="tabpanel" aria-labelledby={`kb-tab-${v}`} style={{ padding: 16 }}>
        Active: {v}
      </div>
    </div>
  )
}
