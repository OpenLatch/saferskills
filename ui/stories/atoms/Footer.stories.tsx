import type { Story } from '@ladle/react';

export const Default: Story = () => (
  <footer
    style={{
      borderTop: '1px solid rgb(var(--border))',
      padding: 24,
      fontSize: 14,
      color: 'rgb(var(--muted-fg))',
    }}
  >
    <div style={{ maxWidth: '80ch', margin: '0 auto', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      <span>Stewarded by OpenLatch</span>
      <span>·</span>
      <a href="#">Source</a>
      <span>·</span>
      <a href="#">Methodology</a>
      <span>·</span>
      <a href="#">Privacy</a>
      <span>·</span>
      <a href="#">Terms</a>
      <span style={{ flex: 1 }}></span>
      <span>© 2026 Apache 2.0</span>
    </div>
  </footer>
);
