import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(root, '../backend');
const deps = path.join(backend, '.deps');
const pythonPath = [backend, existsSync(deps) ? deps : '', process.env.PYTHONPATH || '']
  .filter(Boolean)
  .join(path.delimiter);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    channel: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${process.env.E2E_PYTHON || 'python'} -X utf8 tests/serve_frontend_e2e.py`,
      cwd: backend,
      env: {
        PYTHONPATH: pythonPath,
        E2E_PORT: '8001',
        TMP: path.join(backend, '.pytest_cache'),
        TEMP: path.join(backend, '.pytest_cache'),
      },
      url: 'http://127.0.0.1:8001/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174',
      cwd: root,
      env: { API_PROXY_TARGET: 'http://127.0.0.1:8001' },
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
