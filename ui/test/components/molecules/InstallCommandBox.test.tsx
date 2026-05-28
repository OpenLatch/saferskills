import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import InstallCommandBox from '../../../components/molecules/InstallCommandBox'

describe('InstallCommandBox', () => {
  it('renders the npx command for the slug', () => {
    const { container } = render(<InstallCommandBox slug="acme--foo" />)
    expect(container.querySelector('code')?.textContent).toBe('npx saferskills install acme--foo')
  })

  it('respects an override command', () => {
    const { container } = render(<InstallCommandBox slug="acme--foo" command="curl -sSL https://saferskills.ai/install | sh" />)
    expect(container.querySelector('code')?.textContent).toContain('curl')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<InstallCommandBox slug="acme--foo" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
