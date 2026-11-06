import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Instructions } from "./Instructions";
import { jsonResponse } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows both instruction sets with no edit control", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ queue: "Run the queue.", claim: "Work a claim." }),
      ),
  );
  const { container } = render(<Instructions />);
  expect(await screen.findByText("Run the queue.")).toBeDefined();
  expect(screen.getByText("Work a claim.")).toBeDefined();
  expect(screen.getByText("Running the queue")).toBeDefined();
  expect(screen.getByText("Working a claim")).toBeDefined();
  expect(container.querySelector("textarea")).toBeNull();
  expect(container.querySelector("input")).toBeNull();
  expect(container.querySelector("button")).toBeNull();
});
