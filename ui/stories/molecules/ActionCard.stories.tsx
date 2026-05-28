import type { Story } from '@ladle/react'
import ActionCard from '../../components/molecules/ActionCard'
import Input from '../../components/atoms/Input'
import Button from '../../components/atoms/Button'

export const Find: Story = () => (
  <ActionCard
    index="01"
    kicker="FIND"
    liveLabel="INDEXING"
    title="Search the catalog."
    lede="12,847 skills, MCPs, and plugins indexed from 12+ registries. One search instead of twelve."
  >
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ flex: 1 }}>
        <Input prefix="⌘K" placeholder="Search 12,847 skills…" aria-label="Search catalog" />
      </div>
      <Button as="a" href="/catalog" variant="primary">Browse</Button>
    </div>
  </ActionCard>
)

export const Audit: Story = () => (
  <ActionCard
    index="02"
    kicker="AUDIT"
    liveLabel="RUNNING"
    title="Scan a new skill."
    lede="Paste a public GitHub URL. We return a full security report in ~30 seconds. Free. No account."
  >
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ flex: 1 }}>
        <Input prefix="github.com/" placeholder="org/repo" aria-label="Repository URL" />
      </div>
      <Button as="a" href="/scan" variant="primary">Scan now</Button>
    </div>
  </ActionCard>
)

export const Grid: Story = () => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
    <ActionCard
      index="01"
      kicker="FIND"
      liveLabel="INDEXING"
      title="Search the catalog."
      lede="12,847 skills indexed."
    >
      <Input prefix="⌘K" placeholder="Search…" aria-label="Search catalog" />
    </ActionCard>
    <ActionCard
      index="02"
      kicker="AUDIT"
      liveLabel="RUNNING"
      title="Scan a new skill."
      lede="Paste a public GitHub URL."
    >
      <Input prefix="github.com/" placeholder="org/repo" aria-label="Repository URL" />
    </ActionCard>
  </div>
)
