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
  // The amount and state also appear in the overview, so there is more than one.
  expect(screen.getAllByText("$420.00").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Waiting").length).toBeGreaterThan(0);
});

it("summarises the queue with counts by state and the total claimed", async () => {
  stubFetch(null);
  render(<Queue />);
  expect(await screen.findByText("Overview")).toBeDefined();
  expect(screen.getByText("Total claims")).toBeDefined();
  expect(screen.getByText("Total claimed")).toBeDefined();
  // One waiting claim of $420: the total claimed tile shows its money.
  expect(screen.getAllByText("$420.00").length).toBeGreaterThan(0);
  // Every state is labelled, even those with a count of zero.
  expect(screen.getByText("Decided")).toBeDefined();
  expect(screen.getByText("For handler")).toBeDefined();
});

it("shows the current run's to-do list with every status and the summary", async () => {
  stubFetch(currentRun);
  render(<Queue />);
  expect(await screen.findByText("Current run")).toBeDefined();
  expect(screen.getByText("To do")).toBeDefined();
  expect(screen.getByText("Done")).toBeDefined();
  // "For handler" is both a run item badge and an overview stat label.
  expect(screen.getAllByText("For handler").length).toBeGreaterThan(0);
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
