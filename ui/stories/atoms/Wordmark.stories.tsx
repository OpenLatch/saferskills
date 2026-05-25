import type { Story } from '@ladle/react';

// Wordmark is an Astro component, so Ladle renders its HTML equivalent.
// The visual contract — Crimson Pro 700, cobalt primary, 0 radius — is the
// W1 invariant the designer validates against.

const baseStyle: React.CSSProperties = {
  fontFamily: 'Crimson Pro, Georgia, serif',
  fontWeight: 700,
  color: 'rgb(var(--primary))',
  letterSpacing: '-0.02em',
  lineHeight: 1,
  textDecoration: 'none',
};

export const Hero: Story = () => <span style={{ ...baseStyle, fontSize: 56 }}>SaferSkills</span>;
export const Large: Story = () => <span style={{ ...baseStyle, fontSize: 36 }}>SaferSkills</span>;
export const Medium: Story = () => <span style={{ ...baseStyle, fontSize: 28 }}>SaferSkills</span>;
export const Small: Story = () => <span style={{ ...baseStyle, fontSize: 18 }}>SaferSkills</span>;
