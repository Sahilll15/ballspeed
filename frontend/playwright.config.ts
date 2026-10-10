import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.spec.ts',
  timeout: 120_000,
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: 'http://localhost:5173', ...devices['Desktop Chrome'] },
  webServer: [
    {
      command: 'uv run --project ../backend uvicorn ballspeed.main:app --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
    },
    { command: 'npx vite --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: true },
  ],
})
