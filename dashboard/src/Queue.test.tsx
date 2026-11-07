import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Queue } from "./Queue";
import { currentRun, jsonResponse, queueItem } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(run: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve(
        input === "/api/claims" ? jsonResponse([queueItem]) : jsonResponse(run),
      ),
    ),
  );
}

it("lists claims with their state and money", async () => {
  stubFetch(null);
  render(<Queue />);
  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("Trip Delay")).toBeDefined();
  expect(screen.getByText("$420.00")).toBeDefined();
  expect(screen.getByText("Waiting")).toBeDefined();
});

it("shows the current run's to-do list with every status and the summary", async () => {
  stubFetch(currentRun);
  render(<Queue />);
  expect(await screen.findByText("Current run")).toBeDefined();
  expect(screen.getByText("To do")).toBeDefined();
  expect(screen.getByText("Done")).toBeDefined();
  expect(screen.getByText("For handler")).toBeDefined();
  // "In progress" appears for both a run item and (not here) a claim state.
  expect(screen.getAllByText("In progress").length).toBeGreaterThan(0);
  expect(screen.getByText(currentRun.summary ?? "")).toBeDefined();
  expect(screen.getByText("CLM-1004")).toBeDefined();
});

it("shows no run panel when there is no run", async () => {
  stubFetch(null);
  render(<Queue />);
  await screen.findByText("Claims queue");
  expect(screen.queryByText("Current run")).toBeNull();
});

it("shows a message instead of staying stuck when the backend is unreachable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("network down"))),
  );
  render(<Queue />);
  expect(
    await screen.findByText("Could not reach the backend. Retrying."),
  ).toBeDefined();
});
