import { defineConfig, devices } from '@playwright/test';

function portFromEnvironment(name: string, fallback: number) {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(value) || value < 1 || value > 65_535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return value;
}

const apiPort = portFromEnvironment('GROUNDEDPDF_E2E_API_PORT', 18_000);
const webPort = portFromEnvironment('GROUNDEDPDF_E2E_WEB_PORT', 15_173);
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const webOrigin = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: webOrigin,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `../../.venv/bin/python ../../scripts/prepare_e2e.py && cd ../api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiOrigin}/api/v1/health`,
      reuseExistingServer: false,
      env: {
        GROUNDEDPDF_ENVIRONMENT: 'test',
        GROUNDEDPDF_MODEL_PROVIDER: 'mock',
        GROUNDEDPDF_DATA_DIR: '../../data/e2e',
        GROUNDEDPDF_DATABASE_URL: 'sqlite:///../../data/e2e/groundedpdf.db',
        GROUNDEDPDF_CORS_ORIGINS: JSON.stringify([webOrigin]),
      },
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      url: webOrigin,
      reuseExistingServer: false,
      env: {
        VITE_API_BASE_URL: `${apiOrigin}/api/v1`,
      },
    },
  ],
});
