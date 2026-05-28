import type { ReactNode } from 'react'

interface Props {
  index: string
  tag: string
  body: ReactNode
  metaLines?: ReactNode[]
}

/**
 * 3-column "Why SaferSkills" row. 220px tag col + 1fr body + 260px meta col.
 * Hairline borders top/bottom. Body uses `<b>` for highlights.
 */
export default function WhyRow({ index, tag, body, metaLines = [] }: Props) {
  return (
    <div className="why-row">
      <div className="why-tag">
        <span className="n">{index}</span>
        <span className="l">{tag}</span>
      </div>
      <div className="why-body">{body}</div>
      <div className="why-meta">
        {metaLines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  )
}
