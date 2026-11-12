import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// BLOCKCUT_API lets a parallel agent point its own dev UI at its own API port (default: the shared :8787).
const api = process.env.BLOCKCUT_API ?? 'http://127.0.0.1:8787'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': api, '/assets': api, '/media': api, '/music': api, '/footage': api, '/renders': api } },
})
