import { useEffect, useRef, useState } from 'react'

interface Props {
  base: string
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
  base,
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
  const wordRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!respectsReducedMotion || typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [respectsReducedMotion])

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

  if (reducedMotion) {
    return (
      <h1 className="h-display rotating-headline reduced">
        {base}{' '}
        <span className="rotator">
          <span className="rotator-word">{nouns.join(' · ')}</span>
        </span>
        {trailing}
      </h1>
    )
  }

  const stateClass = state === 'idle' ? '' : state
  return (
    <h1
      className="h-display rotating-headline"
      onMouseEnter={pauseOnHover ? () => setPaused(true) : undefined}
      onMouseLeave={pauseOnHover ? () => setPaused(false) : undefined}
    >
      {base}{' '}
      <span className="rotator">
        <span
          ref={wordRef}
          className={`rotator-word ${stateClass}`.trim()}
        >
          {nouns[index]}
        </span>
      </span>
      {trailing}
    </h1>
  )
}
