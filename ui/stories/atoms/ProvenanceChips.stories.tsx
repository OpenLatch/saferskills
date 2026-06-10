import type { Story } from '@ladle/react'
import ProvenanceChips from '../../components/atoms/ProvenanceChips'

export const Default: Story = () => (
  <div style={{ padding: 40 }}>
    <ProvenanceChips
      chips={[
        { label: 'OWASP Agentic', title: 'Graded against the OWASP Top 10 for Agentic Apps.' },
        { label: 'MITRE ATLAS', title: 'Adversarial techniques mapped to MITRE ATLAS.' },
        { label: 'Cloud-validated · Client-administered', title: 'Ran on the client; we graded.', tone: 'tier' },
        { label: 'Apache-2.0', title: 'Open-source methodology + engine.', tone: 'pack' },
      ]}
    />
  </div>
)
