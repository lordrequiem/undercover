import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Instructions } from "./Instructions";
import { jsonResponse } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the instruction text with no edit control", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ instructions: "Work the claims queue." }),
      ),
  );
  const { container } = render(<Instructions />);
  expect(await screen.findByText("Work the claims queue.")).toBeDefined();
  expect(container.querySelector("textarea")).toBeNull();
  expect(container.querySelector("input")).toBeNull();
  expect(container.querySelector("button")).toBeNull();
});
