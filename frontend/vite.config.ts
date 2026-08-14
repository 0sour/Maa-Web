import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

// ── Maa-Web frontend Vite config ────────────────────────────
// Dev proxy: /api → backend (http://localhost:8000)
//            /ws  → backend WebSocket (same origin on Nginx prod)
// Output: dist/  → copied into nginx image as /usr/share/nginx/html
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // WebSocket upgrade for /api/v1/tasks/ws/logs (log streaming)
        ws: true,
      },
      '/healthz': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2020',
    sourcemap: mode !== 'production',
    outDir: 'dist',
    // NAS may have slightly older browsers (Safari on older iPad etc.), avoid too-modern syntax
    cssCodeSplit: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          axios: ['axios'],
        },
      },
    },
  },
}))
