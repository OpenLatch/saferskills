import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import DetectorCard from '../../../components/molecules/DetectorCard'

describe('DetectorCard', () => {
  it('renders rule_id + status', () => {
    const { container } = render(
      <DetectorCard ruleId="SS-MCP-POISON-UNICODE-TAG-01" status="running" filePath="tools/manifest.json" />,
    )
    expect(container.querySelector('.detector-card-rule')?.textContent).toBe('SS-MCP-POISON-UNICODE-TAG-01')
    expect(container.querySelector('.detector-card-path')?.textContent).toBe('tools/manifest.json')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<DetectorCard ruleId="SS-X-Y-01" status="completed" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
