import { defineConfig, devices } from '@playwright/test';

import { API_PORT, WEB_PORT, backend, baseURL, frontend, python, serverEnv } from './stack.mjs';

const ci = Boolean(process.env.CI);

export default defineConfig({
  testDir: './tests',
  // The tests share one database and the journey tests build on each other's records.
  fullyParallel: false,
  workers: 1,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: ci
    ? [['github'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    locale: 'en-US',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    {
      name: 'phone',
      use: { ...devices['Pixel 7'] },
      // The screens are the same code on a phone; what differs is the layout.
      testMatch: /smoke\.spec\.ts/,
    },
  ],
  webServer: [
    {
      command: `"${python}" manage.py runserver 127.0.0.1:${API_PORT} --noreload`,
      cwd: backend,
      env: serverEnv as Record<string, string>,
      url: `http://127.0.0.1:${API_PORT}/api/health/`,
      reuseExistingServer: !ci,
      stdout: 'ignore',
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      cwd: frontend,
      env: {
        ...process.env,
        VITE_DEV_API_PROXY: `http://127.0.0.1:${API_PORT}`,
      } as Record<string, string>,
      url: baseURL,
      reuseExistingServer: !ci,
      stdout: 'ignore',
      timeout: 120_000,
    },
  ],
});
