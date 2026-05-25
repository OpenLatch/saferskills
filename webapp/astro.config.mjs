import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// https://astro.build/config
export default defineConfig({
  output: 'static',
  site: 'https://saferskills.ai',
  integrations: [react()],
  vite: {
    plugins: [],
  },
  server: {
    port: 5173,
    host: true,
  },
});
