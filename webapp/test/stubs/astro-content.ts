// Vitest resolution stub for the virtual `astro:content` module (which only
// exists inside the Astro build). Tests that need real entries `vi.mock` it with
// a factory; this just gives Vite something to resolve so import-analysis passes.
export async function getCollection(): Promise<unknown[]> {
  return []
}
