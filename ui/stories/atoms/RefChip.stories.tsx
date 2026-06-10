import type { Story } from '@ladle/react'
import RefChip from '../../components/atoms/RefChip'

export const Owasp: Story = () => (
  <div style={{ padding: 40, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
    <RefChip label="ASI04:2026" href="https://genai.owasp.org/" kind="owasp" />
    <RefChip label="LLM01:2025" href="https://genai.owasp.org/llm-top-10/" kind="owasp" />
    <RefChip label="AML.T0053" href="https://atlas.mitre.org/techniques/AML.T0053" kind="mitre" />
    <RefChip label="NIST AI 600-1" href="https://www.nist.gov/" kind="nist" />
  </div>
)
