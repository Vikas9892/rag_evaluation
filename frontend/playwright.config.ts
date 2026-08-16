import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * These tests need the real API and a real index — they exist to catch what
 * the mocked unit tests cannot: that an upload actually reaches the worker,
 * that indexing actually finishes, and that a question against the uploaded
 * corpus is answered from the uploaded documents. Nothing here is stubbed.
 *
 * The servers are started by hand rather than by `webServer`: indexing state
 * lives on disk, and a runner that tore the API down between runs would also
 * decide when a user's uploads disappear.
 */
export default defineConfig({
  testDir: "./e2e",
  // One worker: the tests share one corpus on one filesystem, and two of them
  // uploading at once would race over the same index.
  workers: 1,
  fullyParallel: false,
  // A cold sweep embeds and indexes real documents; the default 30s is a
  // timeout on the model loading, not on anything being wrong.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
