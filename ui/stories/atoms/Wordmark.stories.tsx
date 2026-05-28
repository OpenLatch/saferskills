import type { Story } from '@ladle/react'

// Wordmark is an Astro component. The Ladle visual contract: Onest 600
// monochrome (slate-900 on light, white on dark), logo + label flexed left.
const baseStyle: React.CSSProperties = {
  fontFamily: 'Onest, system-ui, sans-serif',
  fontWeight: 600,
  color: 'var(--fg-1, #0F172A)',
  letterSpacing: '-0.02em',
  lineHeight: 1,
  textDecoration: 'none',
  display: 'inline-flex',
  alignItems: 'center',
}

const cell = (logoPx: number, textPx: number, gap: number) => (
  <span style={{ ...baseStyle, gap }}>
    <img src="/logos/saferskills-logo.svg" alt="" aria-hidden="true" width={logoPx} height={logoPx} />
    <span style={{ fontSize: textPx }}>SaferSkills</span>
  </span>
)

// Logo:text ratio ≈ 0.8 — logo height tracks the wordmark's cap-height plus
// a small optical buffer. Matches the production Wordmark.astro sizing table.
export const Hero: Story = () => cell(42, 52, 14)
export const Large: Story = () => cell(30, 36, 12)
export const Medium: Story = () => cell(20, 24, 10)
export const Small: Story = () => cell(14, 16, 8)
