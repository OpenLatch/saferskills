// Resolve the native `saferskills` binary: first the platform-specific optional
// dependency (@openlatch/saferskills-{platform}), then the postinstall fallback
// under ../bin/. Pure Node stdlib — runs during `npm install` postinstall and
// at every launch.

const path = require('path')
const os = require('os')

const PLATFORMS = {
  'darwin-arm64': '@openlatch/saferskills-darwin-arm64',
  'darwin-x64': '@openlatch/saferskills-darwin-x64',
  'linux-x64': '@openlatch/saferskills-linux-x64',
  'linux-arm64': '@openlatch/saferskills-linux-arm64',
  'win32-x64': '@openlatch/saferskills-win32-x64',
}

function resolveBinary(baseName) {
  const platformKey = `${os.platform()}-${os.arch()}`
  const pkg = PLATFORMS[platformKey]

  if (!pkg) {
    console.error(
      `${baseName}: unsupported platform ${platformKey}. ` +
        `Supported: ${Object.keys(PLATFORMS).join(', ')}`
    )
    process.exit(1)
  }

  const ext = os.platform() === 'win32' ? '.exe' : ''
  const binaryName = `${baseName}${ext}`

  try {
    const pkgDir = path.dirname(require.resolve(`${pkg}/package.json`))
    return path.join(pkgDir, binaryName)
  } catch {
    // Optional dependency not installed (--no-optional, Yarn PnP, corporate
    // proxy, etc.); fall back to the postinstall-downloaded binary.
    return path.join(__dirname, '..', 'bin', binaryName)
  }
}

module.exports = { resolveBinary, PLATFORMS }
