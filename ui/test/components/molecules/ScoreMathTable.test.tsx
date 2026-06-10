import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ScoreMathTable from '../../../components/molecules/ScoreMathTable'

const MODS = [
  { testId: 'AS-06', severity: 'critical', delta: -40, emphasized: true },
  { testId: 'AS-09', severity: 'high', delta: -25 },
]

describe('ScoreMathTable', () => {
  it('renders base, signed modifiers and the reconciled total', () => {
    const { container } = render(
      <ScoreMathTable base={100} modifiers={MODS} finalScore={35} />
    )
    expect(screen.getByText('Base')).toBeInTheDocument()
    expect(screen.getByText('-40')).toBeInTheDocument()
    expect(screen.getByText('35')).toBeInTheDocument()
    // the emphasized row (the finding's own) carries .me
    expect(container.querySelector('.sm-row.me')).not.toBeNull()
    // no cap row when not applied
    expect(container.querySelector('.sm-row.cap')).toBeNull()
  })

  it('shows the worst-finding cap row when the ceiling was applied', () => {
    const { container } = render(
      <ScoreMathTable
        base={100}
        modifiers={MODS}
        cap={{ label: 'Worst-finding cap', value: 15 }}
        finalScore={15}
      />
    )
    expect(container.querySelector('.sm-row.cap')).not.toBeNull()
    expect(screen.getByText('Worst-finding cap')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<ScoreMathTable base={100} modifiers={MODS} finalScore={35} />)
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
