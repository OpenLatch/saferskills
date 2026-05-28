import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ScanStageCard from '../../../components/molecules/ScanStageCard'

describe('ScanStageCard', () => {
  it('renders the stage with status class', () => {
    const { container } = render(
      <ScanStageCard index="01" name="Fetch" status="running" detectorsDone={2} detectorsTotal={6} />,
    )
    expect(container.querySelector('.stage-card-running')).not.toBeNull()
    expect(container.querySelector('.stage-card-name')?.textContent).toBe('Fetch')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <ScanStageCard index="01" name="Fetch" status="completed" detectorsDone={4} detectorsTotal={4} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
