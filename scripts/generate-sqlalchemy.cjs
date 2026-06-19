#!/usr/bin/env node
/**
 * generate-sqlalchemy.cjs — SQLAlchemy 2 ORM model emission.
 *
 * Thin wrapper around the ported Python generator
 * `services/api/scripts/generate_sqlalchemy_models.py` (mirrors
 * openlatch-platform's Jinja2 + KNOWN_ENUMS generator). Walks
 * schemas/*.schema.json, reads x-postgresql-* extensions, and emits full
 * column projections under services/api/app/models/generated/.
 *
 * Replaces the earlier minimal stub (id/created_at/updated_at/metadata only). See
 * .claude/rules/schema-driven-development.md + contributor-docs/codegen.md.
 */
'use strict'

const { spawnSync } = require('node:child_process')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const SERVICES_API = path.join(ROOT, 'services', 'api')

const result = spawnSync('uv', ['run', 'python', 'scripts/generate_sqlalchemy_models.py'], {
  cwd: SERVICES_API,
  stdio: 'inherit',
  shell: true,
})

process.exit(result.status ?? 1)
