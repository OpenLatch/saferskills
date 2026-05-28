import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import VendorResponseBlock from '../../../components/molecules/VendorResponseBlock'

describe('VendorResponseBlock', () => {
  it('renders quote + author + version', () => {
    const { container } = render(
      <VendorResponseBlock
        bodyMarkdown="Acknowledged."
        author="acme"
        submittedAt="2026-05-26T10:00:00Z"
        version={2}
      />,
    )
    expect(container.querySelector('.vendor-response')).not.toBeNull()
    expect(screen.getByText(/acme/i)).toBeInTheDocument()
    expect(container.querySelector('.vendor-response-version')?.textContent).toBe('v2')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <VendorResponseBlock bodyMarkdown="x" author="acme" submittedAt="2026-05-26T10:00:00Z" />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
