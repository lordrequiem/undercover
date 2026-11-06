import type { ClaimDetail, CurrentRun, QueueItem } from "./api";

export const currentRun: CurrentRun = {
  run_id: 1,
  limit: 4,
  finished: true,
  summary: "Worked 4 claims: 2 approve, 1 refer, 1 for_handler.",
  items: [
    {
      claim_id: "CLM-1001",
      status: "done",
      note: "CLM-1001: approve, $420.00",
    },
    { claim_id: "CLM-1002", status: "in_progress", note: "Working the claim." },
    { claim_id: "CLM-1003", status: "to_do", note: "" },
    {
      claim_id: "CLM-1004",
      status: "for_handler",
      note: "Failed twice; left for a handler.",
    },
  ],
};

export const queueItem: QueueItem = {
  claim_id: "CLM-1001",
  customer_name: "Maya Patel",
  plan: "premium",
  claim_type: "trip_delay",
  amount_claimed: 420.0,
  submitted_on: "2026-06-24",
  state: "waiting",
};

export const claimDetail: ClaimDetail = {
  claim_id: "CLM-1001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled by the airline",
  story: "My flight home from Rome was canceled by the airline.",
  items: [
    {
      description: "Airport hotel, one night",
      category: "accommodation",
      amount: 245.0,
    },
  ],
  amount_claimed: 420.0,
  documents: [
    {
      name: "Hotel receipt",
      type: "receipt",
      content: "Hotel Aurelia, one night, $245.00.",
    },
  ],
  state: "decided",
  policy: {
    policy_id: "POL-2001",
    plan: "premium",
    add_ons: [],
    purchased_on: "2026-04-22",
    trip: {
      destination: "Rome, Italy",
      departs_on: "2026-06-10",
      returns_on: "2026-06-18",
      trip_cost: 3100.0,
    },
    travelers: ["Maya Patel"],
  },
  plan: { plan: "premium", name: "UnderCover Premium", deductible: 50.0 },
  customer: {
    name: "Maya Patel",
    email: "maya.patel@example.com",
    previous_claims: [
      {
        claim_id: "CLM-0412",
        filed_on: "2024-08-19",
        claim_type: "baggage_delay",
        summary: "Checked bag arrived late",
        outcome: "approved",
        amount_paid: 140.0,
      },
    ],
  },
  decision: {
    decision: "approve",
    payout: 420.0,
    reason: "Covered under Trip Delay, within the plan maximum.",
    policy_section: "Section 3, Trip Delay",
    signed_off: false,
    paid: null,
  },
  steps: [
    { label: "Picked up the claim", detail: "Opened CLM-1001 from the queue." },
  ],
};

export function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
  });
}
