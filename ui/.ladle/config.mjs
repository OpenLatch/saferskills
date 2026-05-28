/** @type {import('@ladle/react').UserConfig} */
export default {
  // Empty string makes Vite bind HMR WebSocket to 0.0.0.0 (all interfaces) while the
  // client falls back to the page hostname (localhost). Required for Docker port mapping.
  hmrHost: process.env.LADLE_DOCKER === '1' ? '' : undefined,
}
