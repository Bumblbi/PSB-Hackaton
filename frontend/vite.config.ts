import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
      '/health': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
    },
  },
  test: {
    pool: 'threads',
    maxWorkers: 1,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
