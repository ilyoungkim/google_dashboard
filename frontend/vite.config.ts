import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        secure: false,
      },
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        secure: false,
      },
      '/healthz': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
