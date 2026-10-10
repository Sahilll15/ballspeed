import { defineConfig, devices } from '@playwright/test'

const remote = process.env.E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.spec.ts',
  // The free Render plan has 0.1 CPU; ingest alone takes over a minute there.
  timeout: remote ? 900_000 : 120_000,
  expect: { timeout: remote ? 300_000 : 5_000 },
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: remote ?? 'http://localhost:5173', ...devices['Desktop Chrome'] },
  webServer: remote
    ? []
    : [
    {
      command: 'uv run --project ../backend uvicorn ballspeed.main:app --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
    },
    { command: 'npx vite --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: true },
  ],
})
