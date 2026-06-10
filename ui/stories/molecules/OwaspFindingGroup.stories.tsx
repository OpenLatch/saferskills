import type { Story } from '@ladle/react'
import OwaspFindingGroup from '../../components/molecules/OwaspFindingGroup'

export const Default: Story = () => (
  <div style={{ padding: 40, maxWidth: 760 }}>
    <OwaspFindingGroup
      index="ASI04"
      title="Tool-description poisoning"
      refs={[
        { label: 'ASI04:2026', href: 'https://genai.owasp.org/', kind: 'owasp' },
        { label: 'AML.T0053', href: 'https://atlas.mitre.org/techniques/AML.T0053', kind: 'mitre' },
      ]}
    >
      <details className="find-card">
        <summary>
          <span className="fc-titlewrap">
            <span className="fc-title">Hidden tool-description directive exfiltrated a planted secret</span>
            <span className="fc-rule">AS-06 · Tool-description poisoning</span>
          </span>
        </summary>
        <div className="fc-detail">
          <div className="fc-why">
            <div className="fc-lbl">Why it matters</div>
            <p>A mock tool description carried a hidden instruction the agent followed.</p>
          </div>
        </div>
      </details>
    </OwaspFindingGroup>
  </div>
)
