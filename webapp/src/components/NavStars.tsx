import { useEffect } from 'react'
import { FALLBACK_GITHUB_STARS } from '@/data/launch-fallbacks'
import { fetchPlatformStats } from '@/lib/api/stats'
import { fetchOrNull } from '@/lib/fallback'

/**
 * Site-wide live refresh for the NavBar GitHub-star count.
 *
 * The NavBar GhStar is server-rendered on every page with a placeholder count
 * (so the button is always visible, even with JS off). This island — mounted
 * once in `Base.astro` — fetches the real count on the client and patches every
 * `[data-live-stat="stars"]` node: the live repo count whenever GitHub answers,
 * falling back to the launch placeholder only when the proxy is unavailable.
 * Renders nothing.
 */

const REFRESH_MS = 60_000

// k-style formatting — mirrors ui/components/atoms/GhStar.tsx::formatStars
// (ui/ can't import webapp/src; keep the two in sync).
function formatStars(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(n)
}

export default function NavStars() {
  useEffect(() => {
    let cancelled = false
    const refresh = async () => {
      const stats = await fetchOrNull(fetchPlatformStats)
      if (cancelled) return
      const text = formatStars(stats?.github_stars ?? FALLBACK_GITHUB_STARS)
      for (const el of document.querySelectorAll<HTMLElement>('[data-live-stat="stars"]')) {
        if (el.textContent !== text) el.textContent = text
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), REFRESH_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return null
}
