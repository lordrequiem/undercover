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
