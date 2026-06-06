import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const frontendPort = Number(process.env.VITE_DEV_SERVER_PORT || 5173)
const backendPort = Number(process.env.VITE_BACKEND_PORT || 8000)
const backendTarget = `http://127.0.0.1:${backendPort}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': backendTarget,
      '/health': backendTarget,
    },
  },
})
