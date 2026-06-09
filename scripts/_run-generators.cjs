#!/usr/bin/env node
/**
 * _run-generators.cjs — orchestrator for `pnpm run generate`.
 *
 * Runs the 9 codegen steps in dependency order. Aborts on the first failure.
 * Each step is itself a CommonJS script under scripts/ — keep them small +
 * single-responsibility per .claude/rules/schema-driven-development.md.
 *
 * Step 0 (`source-registry`) rewrites the two ingestion enum arrays in the
 * schema JSON that `validate`/`pydantic` consume, and emits the Python provider
 * registry that `openapi` (imports the FastAPI app → loader.py) needs — so it
 * must run first.
 */
'use strict'

const { execFileSync } = require('node:child_process')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')

const STEPS = [
  ['source-registry', 'generate-ingestion-sources.cjs'],
  ['validate', 'validate-schemas.cjs'],
  ['pydantic', 'generate-pydantic.cjs'],
  ['sqlalchemy', 'generate-sqlalchemy.cjs'],
  ['openapi', 'generate-openapi.cjs'],
  ['ts-types', 'generate-ts-types.cjs'],
  ['zod', 'generate-zod.cjs'],
  ['methodology', 'generate-methodology.cjs'],
  ['agent-pack', 'generate-agent-pack.cjs'],
]

for (const [label, file] of STEPS) {
  const script = path.join(ROOT, 'scripts', file)
  console.log(`\n▶ ${label} (${file})`)
  try {
    execFileSync('node', [script], { stdio: 'inherit', cwd: ROOT })
  } catch (err) {
    console.error(`\n✗ ${label} failed.`)
    process.exit(err.status || 1)
  }
}

console.log('\n✓ All generators succeeded.')
