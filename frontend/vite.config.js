import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on every network interface, not just loopback, so the app is
    // reachable from other devices on the LAN (phones, another laptop) at
    // http://<this-machine-ip>:5173 as well as http://localhost:5173.
    host: true,
    // The API calls below are proxied by this dev server, which runs on this
    // machine, so the backend target stays localhost even for LAN visitors.
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:5000",
        changeOrigin: true,
      },
      "/embeddings": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:5000",
        changeOrigin: true,
      },
      "/query": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:5000",
        changeOrigin: true,
      },
    },
  },
})
