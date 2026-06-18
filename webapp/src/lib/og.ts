import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

import { Resvg } from '@resvg/resvg-js'
import satori from 'satori'

import { TIER_HEX } from '@/lib/tier'

const require = createRequire(import.meta.url)

/** Resolve a bundled @fontsource woff to an absolute path (no CDN). */
function fontFile(pkg: string, file: string): Buffer {
  const pkgRoot = dirname(require.resolve(`${pkg}/package.json`))
  return readFileSync(join(pkgRoot, 'files', file))
}

// Read once at module load; reused across requests (server-side, prerender=false).
const FONTS = [
  {
    name: 'DM Sans',
    data: fontFile('@fontsource/dm-sans', 'dm-sans-latin-400-normal.woff'),
    weight: 400 as const,
    style: 'normal' as const,
  },
  {
    name: 'DM Sans',
    data: fontFile('@fontsource/dm-sans', 'dm-sans-latin-800-normal.woff'),
    weight: 800 as const,
    style: 'normal' as const,
  },
  {
    name: 'Space Mono',
    data: fontFile('@fontsource/space-mono', 'space-mono-latin-400-normal.woff'),
    weight: 400 as const,
    style: 'normal' as const,
  },
]

// Minimal satori VDOM node type (avoids a JSX runtime in a .ts endpoint).
type Node = {
  type: string
  props: { style?: Record<string, unknown>; children?: Node | Node[] | string }
}

const el = (
  type: string,
  style: Record<string, unknown>,
  children?: Node | Node[] | string
): Node => ({ type, props: { style, children } })

export interface OgCardInput {
  displayName: string
  score: number | null
  tier: string
  footer: string
}

/** Render a 1200×630 OG card PNG for a scan/item. */
export async function renderOgCard({
  displayName,
  score,
  tier,
  footer,
}: OgCardInput): Promise<Buffer> {
  const tierColor = TIER_HEX[tier] ?? TIER_HEX.unscoped
  const scoreText = score === null ? '—' : String(score)

  const tree = el(
    'div',
    {
      display: 'flex',
      flexDirection: 'column',
      width: 1200,
      height: 630,
      background: '#0F172A',
      padding: 80,
      fontFamily: 'DM Sans',
    },
    [
      // Wordmark row
      el('div', { display: 'flex', alignItems: 'center', gap: 18 }, [
        el('div', { display: 'flex', width: 52, height: 52, background: '#0D9488' }, ''),
        el('div', { fontSize: 40, fontWeight: 800, color: '#F8FAFC' }, 'SaferSkills'),
      ]),
      // Item name
      el(
        'div',
        {
          display: 'flex',
          marginTop: 56,
          fontSize: 64,
          fontWeight: 800,
          color: '#F8FAFC',
          letterSpacing: '-0.03em',
          lineHeight: 1.05,
        },
        displayName
      ),
      // Score + tier
      el('div', { display: 'flex', alignItems: 'flex-end', gap: 24, marginTop: 32 }, [
        el(
          'div',
          {
            display: 'flex',
            fontSize: 168,
            fontWeight: 800,
            color: tierColor,
            letterSpacing: '-0.05em',
            lineHeight: 1,
          },
          scoreText
        ),
        el(
          'div',
          {
            display: 'flex',
            fontSize: 30,
            color: '#94A3B8',
            fontFamily: 'Space Mono',
            paddingBottom: 28,
          },
          `/100 · ${tier.toUpperCase()}`
        ),
      ]),
      // Footer
      el(
        'div',
        {
          display: 'flex',
          marginTop: 'auto',
          fontSize: 22,
          color: '#0D9488',
          fontFamily: 'Space Mono',
        },
        footer
      ),
    ]
  )

  const svg = await satori(tree as unknown as Parameters<typeof satori>[0], {
    width: 1200,
    height: 630,
    fonts: FONTS,
  })

  return Buffer.from(new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng())
}

export const OG_HEADERS = {
  'Content-Type': 'image/png',
  'Cache-Control': 'public, s-maxage=86400, stale-while-revalidate=604800',
  'X-Robots-Tag': 'noindex',
}
