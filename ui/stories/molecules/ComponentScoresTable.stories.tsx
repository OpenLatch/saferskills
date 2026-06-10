import type { Story } from '@ladle/react'
import ComponentScoresTable from '../../components/molecules/ComponentScoresTable'

export const Populated: Story = () => (
  <div style={{ padding: 40, maxWidth: 760 }}>
    <ComponentScoresTable
      rows={[
        { kind: 'skill', name: 'pdf-extract', path: 'skills/pdf-extract', score: 82, tier: 'green', slug: 'acme--agent--skill-pdf-extract' },
        { kind: 'mcp_server', name: 'payments', path: 'servers/payments', score: 47, tier: 'orange', slug: 'acme--agent--mcp-server-payments' },
        { kind: 'hook', name: 'pre-commit-guard', path: 'hooks/pre-commit', score: 71, tier: 'yellow', slug: 'acme--agent--hook-pre-commit-guard' },
      ]}
    />
  </div>
)

export const Empty: Story = () => (
  <div style={{ padding: 40, maxWidth: 760 }}>
    <ComponentScoresTable rows={[]} />
  </div>
)
