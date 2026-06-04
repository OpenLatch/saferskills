#!/usr/bin/env node

// Postinstall fallback: download the native binary from the GitHub Release when
// the platform-specific optional dependency was not installed (--no-optional,
// unsupported package manager, corporate proxy).
//
// IMPORTANT: this script MUST NEVER fail the npm install (fail-open principle).

const os = require('os')
const fs = require('fs')
const path = require('path')
const { execSync } = require('child_process')

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@openlatch/saferskills-darwin-arm64',
  'darwin-x64': '@openlatch/saferskills-darwin-x64',
  'linux-x64': '@openlatch/saferskills-linux-x64',
  'linux-arm64': '@openlatch/saferskills-linux-arm64',
  'win32-x64': '@openlatch/saferskills-win32-x64',
}

const RUST_TARGETS = {
  'darwin-arm64': 'aarch64-apple-darwin',
  'darwin-x64': 'x86_64-apple-darwin',
  'linux-x64': 'x86_64-unknown-linux-gnu',
  'linux-arm64': 'aarch64-unknown-linux-gnu',
  'win32-x64': 'x86_64-pc-windows-msvc',
}

function isPlatformPackageInstalled() {
  const platformKey = `${os.platform()}-${os.arch()}`
  const pkg = PLATFORM_PACKAGES[platformKey]
  if (!pkg) return false
  try {
    require.resolve(`${pkg}/package.json`)
    return true
  } catch {
    return false
  }
}

function downloadBinary() {
  if (isPlatformPackageInstalled()) {
    return // platform package already provides the binary
  }

  const platformKey = `${os.platform()}-${os.arch()}`
  const rustTarget = RUST_TARGETS[platformKey]
  if (!rustTarget) {
    console.warn(`saferskills: postinstall skipped — unsupported platform ${platformKey}`)
    return
  }

  const pkgJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'))
  const version = pkgJson.version
  const ext = os.platform() === 'win32' ? '.exe' : ''

  const binDir = path.join(__dirname, '..', 'bin')
  fs.mkdirSync(binDir, { recursive: true })

  const assetName = `saferskills-${rustTarget}${ext}`
  const url = `https://github.com/OpenLatch/saferskills/releases/download/v${version}/${assetName}`
  const dest = path.join(binDir, `saferskills${ext}`)

  console.log(`saferskills: downloading binary for ${platformKey}...`)
  try {
    execSync(`curl -fSL --retry 3 -o "${dest}" "${url}"`, {
      stdio: 'pipe',
      timeout: 30000,
    })
    if (os.platform() !== 'win32') {
      fs.chmodSync(dest, 0o755)
    }
    console.log('saferskills: binary installed successfully')
  } catch {
    console.warn(`saferskills: failed to download binary — you can fetch it manually from ${url}`)
  }
}

try {
  downloadBinary()
} catch (err) {
  // Never fail the npm install — fail-open principle.
  console.warn(`saferskills: postinstall warning — ${err.message}`)
}
