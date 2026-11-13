import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Same CSP as production (Caddyfile) so `npm run preview` surfaces any violation before deploy.
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
const api = { '/api': 'http://127.0.0.1:8000' }

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: api },
  preview: { port: 4173, proxy: api, headers: { 'Content-Security-Policy': CSP } },
  build: { sourcemap: false, outDir: 'dist' },
})
