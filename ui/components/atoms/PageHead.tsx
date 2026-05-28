import type { ReactNode } from 'react'

interface MetaPill {
  label: string
  value: string
}

interface Props {
  eyebrow: string
  title: ReactNode
  lede?: ReactNode
  path?: string
  meta?: MetaPill[]
  className?: string
}

/**
 * Signature page-head strip — eyebrow + giant title + optional lede + path
 * pill + arbitrary info pills. Topped with the 12px tick-ruler accent +
 * 40×40 plus-grid background pattern (handled in components.css::.page-head).
 *
 * Title supports inline `<mark>` (teal-tint underline) + `<span className="script">`
 * (orange Nanum Pen Script accent). Pass via `title` as ReactNode for those.
 */
export default function PageHead({
  eyebrow,
  title,
  lede,
  path,
  meta = [],
  className = '',
}: Props) {
  return (
    <section className={`page-head ${className}`.trim()}>
      <div className="container">
        <div className="ph-eyebrow">{eyebrow}</div>
        <h1 className="ph-title">{title}</h1>
        {lede && <p className="ph-lede">{lede}</p>}
        {(path || meta.length > 0) && (
          <div className="ph-row">
            {path && (
              <span className="ph-path">
                <b>PATH</b> · {path}
              </span>
            )}
            {meta.map((m) => (
              <span className="ph-path" key={`${m.label}-${m.value}`}>
                <b>{m.label}</b> · {m.value}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
