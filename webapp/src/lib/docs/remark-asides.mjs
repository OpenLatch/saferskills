/**
 * remark-asides — map Starlight-style `:::note` / `:::tip` / `:::caution` /
 * `:::danger` container directives to design-system `<aside>` callouts, so docs
 * authors keep writing markdown-native asides (no per-file component conversion).
 *
 * Runs AFTER `remark-directive` (which parses `:::` into `containerDirective`
 * nodes) — see `webapp/astro.config.mjs` markdown.remarkPlugins order. Scoped to
 * markdown/MDX content only; the generated methodology MDX contains zero `:::`
 * directives, so this is a no-op there.
 *
 * Optional custom title: `:::note[Custom title]` (remark-directive flags the
 * first paragraph with `data.directiveLabel`). Styling: `.doc-aside` +
 * `.doc-aside--<type>` in `webapp/src/styles/page-docs.css`.
 *
 * Dependency-free recursive walk (no `unist-util-visit`) to avoid pulling a
 * transitive dep to the top level.
 */
const ASIDE_TYPES = new Set(['note', 'tip', 'caution', 'danger'])
const DEFAULT_LABEL = { note: 'Note', tip: 'Tip', caution: 'Caution', danger: 'Danger' }

function transformAside(node) {
  let label = DEFAULT_LABEL[node.name]
  const first = node.children[0]
  if (first && first.type === 'paragraph' && first.data?.directiveLabel) {
    const text = (first.children ?? [])
      .map((c) => c.value ?? '')
      .join('')
      .trim()
    if (text) label = text
    node.children.shift()
  }
  if (!node.data) node.data = {}
  const data = node.data
  data.hName = 'aside'
  data.hProperties = {
    className: ['doc-aside', `doc-aside--${node.name}`],
  }
  node.children.unshift({
    type: 'paragraph',
    data: { hProperties: { className: ['doc-aside-label'] } },
    children: [{ type: 'text', value: label }],
  })
}

function walk(parent) {
  if (!Array.isArray(parent.children)) return
  for (const node of parent.children) {
    if (node.type === 'containerDirective' && ASIDE_TYPES.has(node.name)) {
      transformAside(node)
    }
    walk(node)
  }
}

export function remarkAsides() {
  return (tree) => {
    walk(tree)
  }
}
