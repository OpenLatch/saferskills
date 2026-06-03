import type { Story } from '@ladle/react'
import ScanTerminal, { type TerminalLine } from '../../components/molecules/ScanTerminal'

const LINES: TerminalLine[] = [
  {
    id: 'cmd',
    kind: 'cmd',
    segments: [{ text: 'saferskills scan ', tone: 'cmd' }, { text: 'github.com/anthropics/skills' }],
  },
  { id: 'fetch', kind: 'ok', segments: [{ text: 'Fetch complete' }] },
  {
    id: 'r1',
    kind: 'run',
    segments: [
      { text: 'SS-SKILL-INJECT-FENCED-RUN-02', tone: 'rule' },
      { text: '  ' },
      { text: 'SKILL.md', tone: 'path' },
    ],
  },
  {
    id: 'r2',
    kind: 'warn',
    segments: [{ text: 'SS-SUPPLY-PIN-DRIFT-03', tone: 'rule' }, { text: '  unpinned dep: requests' }],
  },
]

export const Streaming: Story = () => (
  <div style={{ width: 640, height: 380 }}>
    <ScanTerminal lines={LINES} currentStage="supply chain" />
  </div>
)

export const Complete: Story = () => (
  <div style={{ width: 640, height: 380 }}>
    <ScanTerminal
      lines={[...LINES, { id: 'done', kind: 'done', segments: [{ text: 'scan complete — loading report…' }] }]}
      complete
    />
  </div>
)
