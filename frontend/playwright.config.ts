import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests. The backend is mocked by route interception (e2e/mock-api.ts), so
 * these need nothing running but the frontend, which Playwright starts itself.
 */
const PORT = process.env.E2E_PORT ?? "3100";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  outputDir: "./test-results",
  use: {
    baseURL: `http://localhost:${PORT}`,
    actionTimeout: 15_000,
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    command: `npx next dev -p ${PORT}`,
    url: `http://localhost:${PORT}/welcome`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
