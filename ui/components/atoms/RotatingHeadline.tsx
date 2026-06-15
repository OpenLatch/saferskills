import { type ReactNode, useEffect, useRef, useState } from 'react'

interface Props {
  /** Single-line static text before the rotator. Ignored when `baseLines` is set. */
  base?: string
  /**
   * Multi-line static text (I-5.7 §2a): each entry renders as its own block
   * line (`<span class="rh-line">`); the LAST entry hosts the rotator inline.
   * Backward-compatible — when absent, `base` renders exactly as before.
   */
  baseLines?: string[]
  nouns: string[]
  /** Static text appended after the rotating noun (e.g. "." for sentence end). */
  trailing?: string
  cycleMs?: number
  /** Duration of the slide-out / slide-in transform pass per the mockup. */
  fadeMs?: number
  pauseOnHover?: boolean
  respectsReducedMotion?: boolean
}

/**
 * Rotating-noun homepage hero headline (D-FE-32 + Phase A2 rewrite).
 *
 * Mockup vocabulary: an inline `.rotator` wrapper hosts a single `.rotator-word`
 * span that slides up out of view (`translateY(-108%)`) before the next noun
 * pops in from below (`translateY(108%)`) and settles to baseline. The teal
 * highlight is painted on `.rotator` itself, so the moving word always sits on
 * top of the citron underline-block per the hi-fi.
 *
 * `prefers-reduced-motion: reduce` short-circuits to a static list of all
 * nouns separated by ` · ` — no animation, no rotation.
 */
export default function RotatingHeadline({
  base = '',
  baseLines,
  nouns,
  trailing = '',
  cycleMs = 4000,
  fadeMs = 320,
  pauseOnHover = true,
  respectsReducedMotion = true,
}: Props) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [state, setState] = useState<'idle' | 'out' | 'in'>('idle')
  const [widths, setWidths] = useState<number[]>([])
  const wordRef = useRef<HTMLSpanElement | null>(null)
  const measureRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!respectsReducedMotion || typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [respectsReducedMotion])

  // Pre-measure every noun once so .rotator can transition its width when the
  // visible noun swaps. Without an explicit width, the citron underline jumps
  // instantly to the new noun's intrinsic width — the visible flicker the
  // hi-fi calls out. Re-measure once webfonts settle: a mount-time measure
  // against the fallback font under-reports and clips the wider nouns.
  useEffect(() => {
    if (!measureRef.current) return
    const m = measureRef.current
    let cancelled = false
    const measure = () => {
      const next = nouns.map((n) => {
        m.textContent = n
        return m.offsetWidth
      })
      m.textContent = ''
      setWidths(next)
    }
    measure()
    // Always re-measure once webfonts settle. The mount-time measure can run
    // against the fallback font (narrower) and under-reserve the rotator width,
    // which clips the widest noun — and `fonts.status` can read 'loaded' before
    // the display weight is actually applied, so the correction must never be
    // gated on it.
    if (typeof document !== 'undefined' && document.fonts?.ready) {
      document.fonts.ready.then(() => {
        if (!cancelled) measure()
      })
    }
    // The headline font-size is viewport-relative (clamp vw), so noun widths
    // change on resize — re-measure (rAF-throttled) to keep the reserved width
    // exact and avoid a clipped or over-wide underline.
    let raf = 0
    const onResize = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        if (!cancelled) measure()
      })
    }
    window.addEventListener('resize', onResize)
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
    }
  }, [nouns])

  useEffect(() => {
    if (reducedMotion || paused || nouns.length <= 1) return
    const interval = setInterval(() => {
      // 1. slide current word UP and fade
      setState('out')
      // 2. swap the noun and place the new one BELOW the baseline (instant)
      setTimeout(() => {
        setIndex((i) => (i + 1) % nouns.length)
        setState('in')
        // 3. on the next frame, drop `in` so the transition slides it up to baseline
        requestAnimationFrame(() => {
          requestAnimationFrame(() => setState('idle'))
        })
      }, fadeMs)
    }, cycleMs)
    return () => clearInterval(interval)
  }, [reducedMotion, paused, nouns.length, cycleMs, fadeMs])

  // Renders the static base text around the rotator span. Multi-line mode
  // (`baseLines`) emits one `.rh-line` block per entry, the last carrying the
  // rotator inline; single-line mode keeps the original `{base}{rotator}` flow.
  const renderBase = (rotator: ReactNode): ReactNode => {
    if (baseLines && baseLines.length > 0) {
      const last = baseLines.length - 1
      return baseLines.map((line, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static positional lines
        <span key={i} className="rh-line">
          {line}
          {i === last && <> {rotator}</>}
        </span>
      ))
    }
    return (
      <>
        {base}
        {rotator}
      </>
    )
  }

  if (reducedMotion) {
    return (
      <h1 className="h-display rotating-headline reduced">
        {renderBase(
          <span className="rotator-line">
            <span className="rotator">
              <span className="rotator-word">{nouns.join(' · ')}</span>
            </span>
            {trailing}
          </span>,
        )}
      </h1>
    )
  }

  const stateClass = state === 'idle' ? '' : state
  const rotatorWidth = widths[index]
  return (
    <h1
      className="h-display rotating-headline"
      onMouseEnter={pauseOnHover ? () => setPaused(true) : undefined}
      onMouseLeave={pauseOnHover ? () => setPaused(false) : undefined}
    >
      {renderBase(
        <span className="rotator-line">
          <span
            className="rotator"
            style={rotatorWidth ? { width: `${rotatorWidth}px` } : undefined}
          >
            <span
              ref={wordRef}
              className={`rotator-word ${stateClass}`.trim()}
            >
              {nouns[index]}
            </span>
            <span
              ref={measureRef}
              className="rotator-measure"
              aria-hidden="true"
            />
          </span>
          {trailing}
        </span>,
      )}
    </h1>
  )
}
