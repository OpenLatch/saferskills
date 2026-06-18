/**
 * Docs IA — section folder → display label, in sidebar order.
 *
 * Single source of truth for the docs section ordering + labels. KEEP IN
 * LOCKSTEP with the mirror in `webapp/scripts/generate-llms-txt.cjs::SECTIONS`
 * (a `.cjs` can't import this `.ts`). A folder not listed here still ships,
 * appended after these, with a title-cased label.
 */
export interface DocsSection {
  dir: string
  label: string
}

export const DOCS_SECTIONS: DocsSection[] = [
  { dir: 'getting-started', label: 'Getting Started' },
  { dir: 'concepts', label: 'Concepts' },
  { dir: 'find-and-verify', label: 'Find & Verify' },
  { dir: 'agent-scan', label: 'Agent Scan' },
  { dir: 'install', label: 'Install (CLI)' },
  { dir: 'for-authors', label: 'For Authors' },
  { dir: 'security-and-methodology', label: 'Security & Methodology' },
  { dir: 'reference', label: 'Reference' },
]

/** Title-case a folder slug for sections not in DOCS_SECTIONS (fallback). */
export function titleCaseDir(dir: string): string {
  return dir
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
