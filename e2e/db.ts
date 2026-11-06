import path from "node:path";

// A throwaway database for the end-to-end run, reset before each run so the
// backend reseeds and decisions never carry over between runs.
export const E2E_DB = path.resolve("e2e/e2e.db");
