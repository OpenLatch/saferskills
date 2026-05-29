import BandPill from '@ui/components/atoms/BandPill'
import Eyebrow from '@ui/components/atoms/Eyebrow'
import ScoreNumber from '@ui/components/atoms/ScoreNumber'

import { track } from '@/lib/analytics'
import type { CatalogKind, RelatedItem } from '@/lib/api/items'
import { scoredTier, stripeClass } from '@/lib/tier'

interface Props {
  items: RelatedItem[]
  kind: CatalogKind
}

/**
 * Related-items grid (2×2 / 4×1). Same-kind peers computed server-side. Hover
 * lifts the card; clicking emits `catalog_item_clicked`.
 */
export default function RelatedItemsGrid({ items, kind }: Props) {
  if (items.length === 0) return null
  return (
    <div className="container related-items">
      <Eyebrow withRule>RELATED ITEMS</Eyebrow>
      <div className="related-grid">
        {items.slice(0, 4).map((item) => {
          const tier = scoredTier(item.tier)
          return (
            <a
              key={item.slug}
              href={`/items/${item.slug}`}
              className={`related-card ${stripeClass(item.tier)}`.trim()}
              onClick={() => track('catalog_item_clicked', { tier: item.tier ?? 'unscoped', kind })}
            >
              <span className="r-name">{item.display_name}</span>
              <div className="r-score-row">
                {item.aggregate_score != null && (
                  <ScoreNumber size="sm" value={item.aggregate_score} />
                )}
                {tier ? <BandPill tier={tier} /> : <span className="r-unscored">UNSCORED</span>}
              </div>
            </a>
          )
        })}
      </div>
    </div>
  )
}
