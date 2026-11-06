import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ClaimDetail } from "./ClaimDetail";
import { claimDetail, jsonResponse } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the story, items, policy and decision", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(claimDetail)));
  render(<ClaimDetail claimId="CLM-1001" />);
  expect(await screen.findByText(claimDetail.story)).toBeDefined();
  expect(screen.getByText("Airport hotel, one night")).toBeDefined();
  expect(screen.getByText("POL-2001")).toBeDefined();
  expect(screen.getByText("Section 3, Trip Delay")).toBeDefined();
  expect(screen.getByText("Approve")).toBeDefined();
  expect(screen.getAllByText("$420.00").length).toBeGreaterThan(0);
  expect(screen.getByText("Picked up the claim")).toBeDefined();
});

it("marks a claim as working while it is in progress", async () => {
  const working = {
    ...claimDetail,
    state: "in_progress" as const,
    decision: null,
    steps: [{ label: "Picked up the claim", detail: "Opened CLM-1001." }],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(working)));
  render(<ClaimDetail claimId="CLM-1001" />);
  expect(await screen.findByText("Working on the claim.")).toBeDefined();
  expect(screen.getByText("Picked up the claim")).toBeDefined();
});

it("shows the for-handler state and the sections the agent read", async () => {
  const handed = {
    ...claimDetail,
    state: "for_handler" as const,
    decision: null,
    steps: [
      {
        label: "Picked up the claim",
        detail: "Opened CLM-1001 from the queue.",
      },
      { label: "Read the manual", detail: "9. Repeat claims" },
    ],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(handed)));
  render(<ClaimDetail claimId="CLM-1001" />);
  expect(await screen.findByText("For handler")).toBeDefined();
  expect(screen.getByText("Read the manual")).toBeDefined();
  expect(screen.getByText("9. Repeat claims")).toBeDefined();
});

it("omits the decision panel when there is no decision", async () => {
  const pending = {
    ...claimDetail,
    decision: null,
    steps: [],
    state: "waiting" as const,
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(pending)));
  render(<ClaimDetail claimId="CLM-1001" />);
  await screen.findByText(pending.story);
  expect(screen.queryByText("Decision")).toBeNull();
});
