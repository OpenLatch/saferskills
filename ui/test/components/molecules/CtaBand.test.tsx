import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CtaBand from '../../../components/molecules/CtaBand'

describe('CtaBand', () => {
  it('renders title + primary action; lede + secondary action when provided', () => {
    render(
      <CtaBand
        title="Audit the pieces. Scan the whole. Decide."
        lead="Free. No account."
        primaryAction={{ label: 'Scan now', href: '/scan' }}
        secondaryAction={{ label: 'Methodology', href: '/methodology' }}
      />,
    )
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(
      'Audit the pieces. Scan the whole. Decide.',
    )
    expect(screen.getByText(/free.*no account/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Scan now' })).toHaveAttribute('href', '/scan')
    expect(screen.getByRole('link', { name: 'Methodology' })).toHaveAttribute('href', '/methodology')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <CtaBand
        title="Hello"
        primaryAction={{ label: 'Go', href: '/' }}
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
