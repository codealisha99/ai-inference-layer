import { defineConfig } from '@playwright/test';

const testEnvironment = {
  DATABASE_URL: '', DATABASE_URL_UNPOOLED: '', DATABASE_PATH: '',
  HOST: '127.0.0.1', LOG_LEVEL: 'warning', RATE_LIMIT_PER_MINUTE: '',
};

export default defineConfig({
  testDir: './tests/ui',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 15000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3125',
    channel: 'chrome',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    { command: 'npm run build && python3 -m http.server 3127 --bind 127.0.0.1 --directory public', url: 'http://127.0.0.1:3127', reuseExistingServer: false },
    { command: 'uv run --directory ai-inference-server-py python -m src.server', url: 'http://127.0.0.1:3125/health', env: { ...testEnvironment, PORT: '3125', API_KEY: '' }, reuseExistingServer: false },
    { command: 'uv run --directory ai-inference-server-py python -m src.server', url: 'http://127.0.0.1:3126/health', env: { ...testEnvironment, PORT: '3126', API_KEY: 'local-ui-test-key' }, reuseExistingServer: false },
  ],
});
