import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Tailwind v4 is wired in as a Vite plugin — there is no tailwind.config.js.
// The production build goes straight into the Python package (maestarr/web),
// which FastAPI serves; nothing runs on Node in production.
const backend = 'http://127.0.0.1:8709'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
      '/mcp': { target: backend, changeOrigin: true },
    },
  },
  build: {
    outDir: '../maestarr/web',
    emptyOutDir: true,
    sourcemap: false,
  },
})
