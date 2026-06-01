import type { Story } from '@ladle/react'
import Breadcrumb from '../../components/atoms/Breadcrumb'

export const ItemDetail: Story = () => (
  <Breadcrumb
    items={[
      { label: 'Catalog', href: '/catalog' },
      { label: 'MCP Servers', href: '/catalog?kind=mcp_server' },
      { label: 'stripe-mcp' },
    ]}
  />
)

export const Respond: Story = () => (
  <Breadcrumb
    items={[
      { label: 'Catalog', href: '/catalog' },
      { label: 'MCP Servers', href: '/catalog?kind=mcp_server' },
      { label: 'stripe-mcp', href: '/items/stripe--stripe-mcp' },
      { label: 'Respond' },
    ]}
  />
)
