import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claimDetail, jsonResponse, queueItem } from "./fixtures";

beforeEach(() => {
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the queue by default and the claim detail on its hash", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve(
        input === "/api/claims"
          ? jsonResponse([queueItem])
          : jsonResponse(claimDetail),
      ),
    ),
  );
  render(<App />);
  expect(await screen.findByText("Claims queue")).toBeDefined();

  window.location.hash = "#/claims/CLM-1001";
  expect(await screen.findByText(claimDetail.story)).toBeDefined();
});
