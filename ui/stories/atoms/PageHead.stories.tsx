import type { Story } from '@ladle/react'
import PageHead from '../../components/atoms/PageHead'

export const Catalog: Story = () => (
  <PageHead
    eyebrow="CATALOG · 01 · /CATALOG"
    title={<>The trusted catalog of <mark className="mark">12,847</mark> indexed skills.</>}
    lede="Search, filter, and compare. Every entry has a transparent score and a quotable evidence trail."
  />
)

export const ScanSubmit: Story = () => (
  <PageHead
    eyebrow="SCAN · 02 · /SCAN"
    title={<>Paste a public GitHub URL. <span className="script">— ~30s</span></>}
    lede="We fetch, analyze, and score. No account, no install, no payment — just a public report."
  />
)

export const ScanReport: Story = () => (
  <PageHead
    eyebrow="SCAN · 03 · /SCANS/AB12CD34"
    title={<>github-mcp <span className="script">— scored</span></>}
    lede="MCP server · modelcontextprotocol · scanned 2026-05-28 at 14:42 UTC."
  />
)
