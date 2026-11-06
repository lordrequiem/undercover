import { rmSync } from "node:fs";
import { defineConfig } from "@playwright/test";
import { E2E_DB } from "./e2e/db";

// Reset the end-to-end database before the backend starts, so it reseeds and no
// decision carries over between runs. The runner loads this config before the
// web server (unlike a Playwright globalSetup, which runs after it); the guard
// keeps worker processes, which re-import the config, from wiping a seeded db.
if (process.env.TEST_WORKER_INDEX === undefined) {
  rmSync(E2E_DB, { force: true });
}

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  workers: 1,
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    {
      command: "uv run -m uvicorn backend.main:app --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      env: { UNDERCOVER_DB: E2E_DB },
    },
    {
      command: "npx vite dashboard --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: true,
    },
  ],
});
