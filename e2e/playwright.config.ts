import { defineConfig, devices } from "@playwright/test";
import * as dotenv from "dotenv";

dotenv.config({ path: "../.env" });

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: 0,              // no retries — flaky = broken
  workers: 1,              // sequential; e2e tests share a seeded DB
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "test-results/junit.xml" }],
  ],
  use: {
    baseURL: process.env.E2E_FRONTEND_URL ?? "http://localhost:5174",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
