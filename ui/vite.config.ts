import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  // Production build is served under a GitHub Pages project subpath.
  // DEPLOY_BASE picks which one — the live demo at anjesh.ai/FlowStrix/,
  // or a dark-launch build at anjesh.ai/FlowStrix/next/ — so a new UI can
  // be built and deployed without touching the live app's files. Dev
  // server stays at the root either way.
  base: command === 'build' ? (process.env.DEPLOY_BASE || '/FlowStrix/') : '/',
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
}))
