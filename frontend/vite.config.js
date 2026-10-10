import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, the dashboard talks to the FastAPI backend through this proxy.
// In production, FastAPI serves the built files itself (same origin).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/omi': 'http://localhost:8000',
    },
  },
})
