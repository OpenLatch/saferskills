#!/usr/bin/env node

// Thin launcher: resolve the prebuilt native binary and hand the terminal to
// it (stdio inherited, exit code preserved). The Rust binary owns all UX.

const { execFileSync } = require('child_process')
const { resolveBinary } = require('./resolve-binary')

const binary = resolveBinary('saferskills')

try {
  execFileSync(binary, process.argv.slice(2), {
    stdio: 'inherit',
    env: process.env,
  })
} catch (err) {
  if (err.status !== null && err.status !== undefined) {
    process.exit(err.status)
  }
  if (err.code === 'ENOENT') {
    console.error(
      `saferskills: binary not found at ${binary}\n` +
        `Try reinstalling: npm install -g saferskills`
    )
    process.exit(1)
  }
  process.exit(1)
}
