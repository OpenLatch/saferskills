<!--
Thanks for opening a PR! Conventional Commits + DCO are required.
See CONTRIBUTING.md for the full contract.
-->

## Summary

<!-- 1-3 sentences. What changed and why. -->

## Type of change

- [ ] `feat` — new functionality
- [ ] `fix` — bug fix
- [ ] `chore` — maintenance, deps, tooling
- [ ] `docs` — documentation only
- [ ] `refactor` — internal change, no behavior diff
- [ ] `test` — adds or refines tests
- [ ] `build` / `ci` — build / CI surface
- [ ] `rubric-change` — adds, modifies, or deprecates a detection rule (requires a prior `03-rule-proposal` RFC)

## Rubric impact

<!-- Only fill if Type of change includes "rubric-change". -->
- Rule ID(s) affected:
- Severity / scoring impact:
- Regression diff (positive + negative fixtures pass):

## Backward compatibility

<!-- Tick what applies. Be explicit about breaking changes. -->
- [ ] No breaking changes for catalog consumers
- [ ] No breaking changes for CLI users
- [ ] No breaking changes for `pnpm run generate` output shape
- [ ] Yes — see "Migration notes" below

## Test plan

<!-- Concrete steps a reviewer would run. -->
- [ ] `pnpm install && pnpm run generate` is idempotent
- [ ] `docker compose up` brings up postgres + api + webapp
- [ ] `curl http://localhost:8000/api/v1/health` returns 200
- [ ] `pnpm test` passes
- [ ] `cd services/api && uv run pytest` passes

## Linked issue

<!-- e.g. Closes #42, Refs #41 -->

## Reviewer checklist

- [ ] Conventional Commits prefix on the title
- [ ] Every commit carries `Signed-off-by:` (DCO)
- [ ] No unintended files (`generated/` changes match `pnpm run generate` output)
- [ ] Documentation updated (README / METHODOLOGY / `.claude/rules/` as relevant)
- [ ] Anti-recommendation rule honoured (no OpenLatch cross-promotion in catalog content)
