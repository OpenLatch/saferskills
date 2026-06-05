#!/usr/bin/env node
/**
 * generate-openapi.cjs — captures FastAPI's runtime OpenAPI doc.
 *
 * Spawns `uv run python -c "..."` to import app.main and serialise
 * app.openapi() to services/api/openapi.json. The JSON is committed and is
 * the source of truth for the TS DTO + Zod generators.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const ROOT = path.resolve(__dirname, '..')
const OUT = path.join(ROOT, 'services', 'api', 'openapi.json')

const script = `
import json, sys
try:
    from app.main import app
except ModuleNotFoundError as e:
    print(f"app.main not importable: {e}", file=sys.stderr)
    sys.exit(2)
sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True))
sys.stdout.write("\\n")
`

let stdout
try {
  stdout = execFileSync('uv', ['run', '--project', 'services/api', 'python', '-c', script], {
    cwd: ROOT,
    encoding: 'utf8',
  })
} catch (err) {
  console.error('[openapi] FastAPI not importable yet (W1 expected).')
  console.error(`  underlying: ${err.message}`)
  // W1 fallback: emit a minimal placeholder so downstream generators have something to chew on.
  const placeholder = {
    openapi: '3.1.0',
    info: { title: 'SaferSkills API', version: '0.0.0-foundation' },
    paths: {},
    components: {},
  }
  fs.writeFileSync(OUT, JSON.stringify(placeholder, null, 2) + '\n')
  console.log(`[openapi] Wrote placeholder ${path.relative(ROOT, OUT)}.`)
  process.exit(0)
}

// Normalize CRLF → LF: Python's text-mode stdout translates \n → \r\n on Windows,
// so the captured bytes carry CRLF there. Writing them verbatim produces a phantom
// whole-file diff vs the LF-normalised index (CI runs on Linux and emits LF). LF-only
// keeps a local Windows `pnpm run generate` byte-identical to CI.
fs.writeFileSync(OUT, stdout.replace(/\r\n/g, '\n'))
console.log(`[openapi] Wrote ${path.relative(ROOT, OUT)}.`)
