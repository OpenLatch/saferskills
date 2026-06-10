import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import OwaspFindingGroup from '../../../components/molecules/OwaspFindingGroup'

describe('OwaspFindingGroup', () => {
  it('renders the OWASP index, family title, ref chips and its children', () => {
    const { container } = render(
      <OwaspFindingGroup
        index="ASI04"
        title="Tool-description poisoning"
        refs={[{ label: 'ASI04:2026', href: 'https://genai.owasp.org/', kind: 'owasp' }]}
      >
        <div data-testid="card">a finding card</div>
      </OwaspFindingGroup>
    )
    expect(screen.getByText('ASI04')).toBeInTheDocument()
    expect(screen.getByText('Tool-description poisoning')).toBeInTheDocument()
    expect(container.querySelector('.og-refs .ref-chip')).not.toBeNull()
    expect(screen.getByTestId('card')).toBeInTheDocument()
  })

  it('omits the refs row when there are none', () => {
    const { container } = render(
      <OwaspFindingGroup index="LLM01" title="Direct injection" refs={[]}>
        <div>child</div>
      </OwaspFindingGroup>
    )
    expect(container.querySelector('.og-refs')).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <OwaspFindingGroup index="ASI04" title="Tool-description poisoning" refs={[]}>
        <div>child</div>
      </OwaspFindingGroup>
    )
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
