import { type APIRequestContext, expect, test } from "@playwright/test";

const BACKEND = "http://localhost:8000";

async function decide(
  request: APIRequestContext,
  claimId: string,
  decision: string,
  payout: number,
) {
  await request.post(`${BACKEND}/api/claims/${claimId}/decision`, {
    data: {
      decision,
      payout,
      reason: "Recorded for the end-to-end test.",
      policy_section: "Section 3, Trip Delay",
    },
  });
}

async function addStep(
  request: APIRequestContext,
  claimId: string,
  label: string,
  detail: string,
) {
  await request.post(`${BACKEND}/api/claims/${claimId}/steps`, {
    data: { label, detail },
  });
}

test("the queue opens a decided claim with its steps and decision", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1001", "approve", 420);
  await addStep(
    request,
    "CLM-1001",
    "Read the claim",
    "Read the story and documents.",
  );
  await addStep(
    request,
    "CLM-1001",
    "Recorded the decision",
    "Approved for $420.00.",
  );

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Claims queue" }),
  ).toBeVisible();
  await page.getByText("CLM-1001").click();

  await expect(page.getByRole("heading", { name: "Decision" })).toBeVisible();
  await expect(page.getByText("Section 3, Trip Delay")).toBeVisible();
  await expect(page.getByText("Recorded the decision").first()).toBeVisible();
});

test("an over-limit approve shows waiting for sign-off", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1010", "approve", 2500);

  await page.goto("/#/claims/CLM-1010");
  await expect(page.getByText("Waiting for sign-off")).toBeVisible();
});
