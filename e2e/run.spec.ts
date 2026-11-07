import { type APIRequestContext, expect, test } from "@playwright/test";

const BACKEND = "http://localhost:8000";

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

async function setItem(
  request: APIRequestContext,
  runId: number,
  claimId: string,
  status: string,
  note: string,
) {
  await request.post(`${BACKEND}/api/runs/${String(runId)}/items/${claimId}`, {
    data: { status, note },
  });
}

// Pre-record a run the way the harness would leave it: a to-do list with mixed
// statuses, a summary, a decided claim with the sections it read, and a claim
// left for a handler. No model is called.
async function recordRun(request: APIRequestContext) {
  await request.post(`${BACKEND}/api/claims/CLM-1002/decision`, {
    data: {
      decision: "approve",
      payout: 500,
      reason: "Covered under Trip Delay.",
      policy_section: "3. Trip Delay",
    },
  });
  await addStep(request, "CLM-1002", "Read the claim", "Read the story.");
  await addStep(request, "CLM-1002", "Read the wording", "3. Trip Delay");
  await addStep(request, "CLM-1002", "Read the manual", "9. Repeat claims");
  await request.post(`${BACKEND}/api/claims/CLM-1005/for_handler`);

  const opened = await request.post(`${BACKEND}/api/runs`, {
    data: { limit: 4 },
  });
  const runId = ((await opened.json()) as { run_id: number }).run_id;
  await request.post(`${BACKEND}/api/runs/${String(runId)}/plan`, {
    data: { claim_ids: ["CLM-1002", "CLM-1003", "CLM-1004", "CLM-1005"] },
  });
  await setItem(
    request,
    runId,
    "CLM-1002",
    "done",
    "CLM-1002: approve, $500.00",
  );
  await setItem(
    request,
    runId,
    "CLM-1003",
    "in_progress",
    "Working the claim.",
  );
  await setItem(
    request,
    runId,
    "CLM-1005",
    "for_handler",
    "Failed twice; left for a handler.",
  );
  await request.post(`${BACKEND}/api/runs/${String(runId)}/finish`, {
    data: { summary: "Worked 4 claims: 1 approve, 1 for_handler." },
  });
}

test("the queue shows the run's to-do list and claims show their steps", async ({
  page,
  request,
}) => {
  await recordRun(request);

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Current run" }),
  ).toBeVisible();
  await expect(
    page.getByText("Worked 4 claims: 1 approve, 1 for_handler."),
  ).toBeVisible();
  await expect(page.getByText("Done")).toBeVisible();
  await expect(page.getByText("To do")).toBeVisible();
  await expect(page.getByText("In progress").first()).toBeVisible();
  await expect(page.getByText("For handler").first()).toBeVisible();

  await page.goto("/#/claims/CLM-1002");
  await expect(page.getByText("Read the manual")).toBeVisible();
  await expect(page.getByText("9. Repeat claims")).toBeVisible();
  await expect(page.getByText("3. Trip Delay").first()).toBeVisible();

  await page.goto("/#/claims/CLM-1005");
  await expect(page.getByText("For handler")).toBeVisible();
});
