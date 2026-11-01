export type ClaimState =
  "waiting" | "in_progress" | "waiting_for_signoff" | "decided";

export interface QueueItem {
  claim_id: string;
  customer_name: string;
  plan: string;
  claim_type: string;
  amount_claimed: number;
  submitted_on: string;
  state: ClaimState;
}

export interface Item {
  description: string;
  category: string;
  amount: number;
}

export interface Document {
  name: string;
  type: string;
  content: string;
}

export interface Decision {
  decision: "approve" | "decline" | "refer";
  payout: number;
  reason: string;
  policy_section: string;
  signed_off: boolean;
  paid: number | null;
}

export interface Step {
  label: string;
  detail: string;
}

export interface PreviousClaim {
  claim_id: string;
  filed_on: string;
  claim_type: string;
  summary: string;
  outcome: string;
  amount_paid: number;
}

export interface Customer {
  name: string;
  email: string;
  previous_claims: PreviousClaim[];
}

export interface Trip {
  destination: string;
  departs_on: string;
  returns_on: string;
  trip_cost: number;
}

export interface Policy {
  policy_id: string;
  plan: string;
  add_ons: string[];
  purchased_on: string;
  trip: Trip;
  travelers: string[];
}

export interface Plan {
  plan: string;
  name: string;
  deductible: number;
}

export interface ClaimDetail {
  claim_id: string;
  claim_type: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  summary: string;
  story: string;
  items: Item[];
  amount_claimed: number;
  documents: Document[];
  state: ClaimState;
  policy: Policy;
  plan: Plan;
  customer: Customer;
  decision: Decision | null;
  steps: Step[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok)
    throw new Error(`${path} returned ${String(response.status)}`);
  return response.json() as Promise<T>;
}

export function fetchQueue(): Promise<QueueItem[]> {
  return getJson<QueueItem[]>("/api/claims");
}

export function fetchClaim(claimId: string): Promise<ClaimDetail> {
  return getJson<ClaimDetail>(`/api/claims/${claimId}`);
}

export async function fetchInstructions(): Promise<string> {
  const data = await getJson<{ instructions: string }>("/api/instructions");
  return data.instructions;
}

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

export function formatMoney(amount: number): string {
  return money.format(amount);
}

const STATE_LABELS: Record<ClaimState, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_signoff: "Waiting for sign-off",
  decided: "Decided",
};

export function stateLabel(state: ClaimState): string {
  return STATE_LABELS[state];
}

export function titleCase(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
