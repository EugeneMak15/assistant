import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/candidates': 'http://localhost:8000',
      '/recommend': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    }
  }
})
