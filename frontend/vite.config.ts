import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  // Vite's default build.assetsDir ("assets") collides with this app's own
  // `/assets` (Asset Inventory) route: nginx's static-file location block for
  // built JS/CSS then shadows the SPA route and the page 404s. Moving built
  // assets to `/static/` keeps the two namespaces disjoint (see nginx.conf).
  build: {
    assetsDir: 'static'
  },
  resolve: {
    alias: {
      'react-router-dom': fileURLToPath(new URL('./src/vendor/react-router-dom.tsx', import.meta.url))
    },
    preserveSymlinks: true
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup/localStorage.ts'],
    include: ['src/tests/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}']
  }
})
