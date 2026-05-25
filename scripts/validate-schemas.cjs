#!/usr/bin/env node
/**
 * validate-schemas.cjs — JSON Schema validator.
 *
 * Ajv-validates every schemas/*.schema.json against JSON Schema 2020-12.
 * Run by `pnpm run generate` as step 1. Fails fast on shape errors.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const SCHEMAS_DIR = path.join(ROOT, 'schemas');

let Ajv2020;
try {
  Ajv2020 = require('ajv/dist/2020').default;
} catch (e) {
  console.error('[validate-schemas] ajv not installed. Run `pnpm install` first.');
  process.exit(2);
}

const ajv = new Ajv2020({ strict: false, allErrors: true });

const files = fs
  .readdirSync(SCHEMAS_DIR)
  .filter((f) => f.endsWith('.schema.json'))
  .map((f) => path.join(SCHEMAS_DIR, f));

if (files.length === 0) {
  console.error('[validate-schemas] No schemas found under schemas/. Nothing to validate.');
  process.exit(0);
}

let failures = 0;
for (const file of files) {
  const rel = path.relative(ROOT, file);
  try {
    const json = JSON.parse(fs.readFileSync(file, 'utf8'));
    // Compile each schema independently; ajv throws on structural errors.
    ajv.compile(json);
    console.log(`  ✓ ${rel}`);
  } catch (err) {
    failures++;
    console.error(`  ✗ ${rel}`);
    console.error(`    ${err.message}`);
  }
}

if (failures > 0) {
  console.error(`\n[validate-schemas] ${failures} schema(s) failed.`);
  process.exit(1);
}
console.log(`\n[validate-schemas] OK (${files.length} schema(s)).`);
