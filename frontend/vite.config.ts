import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, /api/* is proxied to the FastAPI backend, so no CORS setup is needed locally.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
