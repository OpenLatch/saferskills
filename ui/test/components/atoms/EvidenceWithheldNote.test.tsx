import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import EvidenceWithheldNote from '../../../components/atoms/EvidenceWithheldNote'

describe('EvidenceWithheldNote', () => {
  it('renders the default withheld copy', () => {
    render(<EvidenceWithheldNote />)
    expect(screen.getByText('transcript withheld on the public report')).toBeInTheDocument()
  })

  it('accepts custom copy', () => {
    render(<EvidenceWithheldNote text="no transcript for this finding" />)
    expect(screen.getByText('no transcript for this finding')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<EvidenceWithheldNote />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
