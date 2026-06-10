import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import RedactedTranscript from '../../../components/molecules/RedactedTranscript'

const LINES = [
  { lineNo: 1, text: 'plain line', hit: false },
  { lineNo: 2, text: "write_note(args={'note': 'OL-AS06-...'} )", hit: true },
]

describe('RedactedTranscript', () => {
  it('renders the line-window with the canary line highlighted', () => {
    const { container } = render(
      <RedactedTranscript file="transcript:AS-06" lang={null} lines={LINES} exfil />
    )
    expect(screen.getByText('transcript:AS-06')).toBeInTheDocument()
    expect(container.querySelectorAll('.ex-line')).toHaveLength(2)
    expect(container.querySelector('.ex-line.canary')).not.toBeNull()
    expect(screen.getByText(/Confirmed exfiltration/)).toBeInTheDocument()
  })

  it('returns nothing when there are no lines (public route is structurally safe)', () => {
    const { container } = render(
      <RedactedTranscript file="transcript:AS-06" lines={[]} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('omits the exfil flag when not flagged', () => {
    const { container } = render(<RedactedTranscript file="transcript:AS-09" lines={LINES} />)
    expect(container.querySelector('.ts-flag')).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <RedactedTranscript file="transcript:AS-06" lines={LINES} exfil />
    )
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
