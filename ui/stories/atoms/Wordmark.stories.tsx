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

export const Hero: Story = () => cell(80, 52, 16)
export const Large: Story = () => cell(56, 36, 14)
export const Medium: Story = () => cell(40, 24, 12)
export const Small: Story = () => cell(24, 16, 8)
