#!/usr/bin/env node
/**
 * generate-pydantic.cjs — Pydantic v2 model emission.
 *
 * Thin wrapper around the ported Python generator
 * `services/api/scripts/generate_pydantic_models.py` (mirrors
 * openlatch-platform's datamodel-code-generator driver). Emits one Pydantic v2
 * module per schema under services/api/app/schemas/generated/<entity>.py,
 * inheriting OrmBaseModel (snake_case wire format — naming-conventions.md).
 *
 * See .claude/rules/schema-driven-development.md + contributor-docs/codegen.md.
 */
'use strict'

const { spawnSync } = require('node:child_process')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const SERVICES_API = path.join(ROOT, 'services', 'api')

const result = spawnSync('uv', ['run', 'python', 'scripts/generate_pydantic_models.py'], {
  cwd: SERVICES_API,
  stdio: 'inherit',
  shell: true,
})

process.exit(result.status ?? 1)
