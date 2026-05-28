import { useEffect, useState } from 'react'

type Mode = 'light' | 'dark' | 'auto'

/**
 * 3-state theme pill (Light / Dark / Auto). Persists in `localStorage['ss-theme']`;
 * the FOUC-prevention script in `Base.astro` reads the same key before first paint.
 *
 * Auto follows `prefers-color-scheme` live via `matchMedia`.
 */
export default function ThemeToggle() {
  const [mode, setMode] = useState<Mode>('auto')

  useEffect(() => {
    const stored = typeof window === 'undefined' ? null : (() => {
      try { return localStorage.getItem('ss-theme') as Mode | null } catch { return null }
    })()
    setMode(stored && (stored === 'light' || stored === 'dark' || stored === 'auto') ? stored : 'auto')
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try { localStorage.setItem('ss-theme', mode) } catch { /* private mode */ }
    const html = document.documentElement
    html.dataset.themeMode = mode
    const apply = () => {
      const effective = mode === 'auto'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : mode
      html.classList.toggle('dark', effective === 'dark')
    }
    apply()
    if (mode === 'auto') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      mq.addEventListener('change', apply)
      return () => mq.removeEventListener('change', apply)
    }
    return undefined
  }, [mode])

  return (
    <div className="theme-toggle" role="group" aria-label="Theme">
      <button
        type="button"
        aria-label="Light theme"
        aria-pressed={mode === 'light'}
        className={mode === 'light' ? 'active' : ''}
        onClick={() => setMode('light')}
      ><SunIcon /></button>
      <button
        type="button"
        aria-label="Dark theme"
        aria-pressed={mode === 'dark'}
        className={mode === 'dark' ? 'active' : ''}
        onClick={() => setMode('dark')}
      ><MoonIcon /></button>
      <button
        type="button"
        aria-label="System theme"
        aria-pressed={mode === 'auto'}
        className={mode === 'auto' ? 'active' : ''}
        onClick={() => setMode('auto')}
      ><AutoIcon /></button>
    </div>
  )
}

const SunIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
)
const MoonIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
)
const AutoIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3v18" />
    <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none" />
  </svg>
)
