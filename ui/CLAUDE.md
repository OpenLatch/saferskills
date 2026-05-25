# CLAUDE.md — ui/

Shared design system: tokens + framework-agnostic React 19 atoms.

## Hard rules

1. **`styles/tokens.css` is the only color/typography/spacing source.** No magic numbers in components.
2. **Atoms are React 19 + Tailwind primitives only.** Never import Astro APIs from a component under `components/`. (Astro-only thin shells like `Wordmark.astro` are fine as long as they don't introduce dependencies the React side can't link.)
3. **0 radius, 1px borders, no shadows.** Anywhere they appear is a regression — fix at the token, not at the call site.
4. **Anti-recommendation.** No OpenLatch cross-recommendation in catalog content. Footer attribution is the single permitted mention.
5. **Every component ships with a Ladle story + a vitest-axe test.** No exceptions.

See `.claude/rules/design-system.md` for the full contract.
