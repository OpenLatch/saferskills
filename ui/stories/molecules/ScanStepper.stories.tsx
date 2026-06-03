import type { Story } from '@ladle/react'
import ScanStepper, { type ScanStep } from '../../components/molecules/ScanStepper'

const STEPS: ScanStep[] = [
  {
    key: 'fetch',
    index: '01',
    name: 'Fetch',
    tag: 'clone',
    description: 'Clone the repo at the pinned commit and walk every file. Nothing is run.',
    status: 'completed',
    fillPct: 100,
  },
  {
    key: 'security',
    index: '02',
    name: 'Security',
    tag: 'rules',
    description: 'Check each file for prompt-injection, RCE, and secret-exfiltration.',
    status: 'running',
    fillPct: 45,
    runningPct: 45,
  },
  {
    key: 'supply_chain',
    index: '03',
    name: 'Supply chain',
    tag: 'deps',
    description: 'Inspect dependencies for typosquats, drift, and unsigned bundles.',
    status: 'pending',
  },
  {
    key: 'sign',
    index: '04',
    name: 'Score & sign',
    tag: 'verdict',
    description: 'Aggregate the sub-scores under the critical-floor, then sign the report.',
    status: 'pending',
  },
]

export const Running: Story = () => (
  <div style={{ width: 312, border: '1px solid var(--border-2)' }}>
    <ScanStepper steps={STEPS} heading="Stages · 4" currentLabel="security" />
  </div>
)

export const AllComplete: Story = () => (
  <div style={{ width: 312, border: '1px solid var(--border-2)' }}>
    <ScanStepper
      steps={STEPS.map((s) => ({ ...s, status: 'completed', fillPct: 100 }))}
      heading="Stages · 4"
      currentLabel="complete"
    />
  </div>
)
