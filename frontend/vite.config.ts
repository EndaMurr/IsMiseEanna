import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // Mirrors production Caddy's routing: everything server-rendered by
    // web.py (the JSON API plus the login/connect-Garmin server routes)
    // goes to the backend; `npm run dev` needs the same split so it can run
    // against a local `ismiseeanna-web` instance on :8001.
    proxy: {
      '/api': 'http://127.0.0.1:8001',
      '/login': 'http://127.0.0.1:8001',
      '/callback': 'http://127.0.0.1:8001',
      '/logout': 'http://127.0.0.1:8001',
      '/connect': 'http://127.0.0.1:8001',
      '/connect-garmin': 'http://127.0.0.1:8001',
    },
  },
})
