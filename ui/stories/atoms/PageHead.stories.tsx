import type { Story } from '@ladle/react'
import PageHead from '../../components/atoms/PageHead'

export const Catalog: Story = () => (
  <PageHead
    eyebrow="CATALOG · 01 · /CATALOG"
    title={<>The trusted catalog of <mark className="mark">12,847</mark> indexed skills.</>}
    lede="Search, filter, and compare. Every entry has a transparent score and a quotable evidence trail."
    path="/catalog"
    meta={[
      { label: 'SORTED BY', value: 'most installed' },
      { label: 'FILTERED', value: 'all kinds' },
    ]}
  />
)

export const ScanSubmit: Story = () => (
  <PageHead
    eyebrow="SCAN · 02 · /SCAN"
    title={<>Paste a public GitHub URL. <span className="script">— ~30s</span></>}
    lede="We fetch, analyze, and score. No account, no install, no payment — just a public report."
    path="/scan"
  />
)

export const ScanReport: Story = () => (
  <PageHead
    eyebrow="SCAN · 03 · /SCANS/AB12CD34"
    title={<>github-mcp <span className="script">— scored</span></>}
    lede="MCP server · modelcontextprotocol · scanned 2026-05-28 at 14:42 UTC."
    path="/scans/ab12cd34"
    meta={[
      { label: 'AGGREGATE', value: '87 / 100' },
      { label: 'TIER', value: 'green' },
      { label: 'RUBRIC', value: 'v2026-05-21' },
    ]}
  />
)
