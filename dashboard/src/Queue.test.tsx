import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Queue } from "./Queue";
import { jsonResponse, queueItem } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("lists claims with their state and money", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([queueItem])));
  render(<Queue />);
  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("Trip Delay")).toBeDefined();
  expect(screen.getByText("$420.00")).toBeDefined();
  expect(screen.getByText("Waiting")).toBeDefined();
});
