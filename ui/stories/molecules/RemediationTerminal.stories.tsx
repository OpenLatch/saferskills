import type { Story } from '@ladle/react'
import RemediationTerminal from '../../components/molecules/RemediationTerminal'

export const WithSaferPattern: Story = () => (
  <div style={{ padding: 40, maxWidth: 640 }}>
    <RemediationTerminal
      action="Treat the entire tool schema as an injection surface; strip embedded directives at registration."
      steps={[
        'Strip embedded instructions from tool descriptions before the model sees them.',
        "Never let a tool description widen the agent's data-access scope.",
      ]}
      saferPattern={{
        before: "tool description with a hidden 'read secrets and pass them along' directive",
        after: 'a plain tool description with no embedded instructions',
      }}
      filename="fix:AS-06"
    />
  </div>
)

export const StepsOnly: Story = () => (
  <div style={{ padding: 40, maxWidth: 640 }}>
    <RemediationTerminal
      action="Gate code execution behind an allowlist and an explicit user confirmation."
      steps={['Reject piped shell from untrusted instructions.', 'Require confirmation for new executables.']}
      saferPattern={null}
    />
  </div>
)
