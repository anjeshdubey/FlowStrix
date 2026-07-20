import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  // Production build is served under the GitHub Pages project subpath
  // (anjesh.ai/FlowStrix/); dev server stays at the root.
  base: command === 'build' ? '/FlowStrix/' : '/',
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
