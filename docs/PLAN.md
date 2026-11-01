# Plan for the pilot

This plan builds the claims pilot from `docs/SPEC.md`: a backend, a dashboard
and a first UnderCover Agent that works the claims queue the way a handler does.

The work grows in six phases, each building on the last. We build from the
skeleton in `backend/`, `agent/`, `dashboard/` and `e2e/`, keep every check
green as described in `docs/PROCESS.md`, and follow `docs/TECH_STACK.md` and
`docs/CODE_STANDARDS.md`.

## Shape of the work

- **Backend** (`backend/`, FastAPI + SQLite): seeds its database from `data/`,
  serves the queue and claim detail, holds the agent's instructions (read
  only), records decisions and the agent's steps, and owns the one guardrail
  that blocks a payment over the approval limit until a handler signs off.
  Paying is its own operation that takes the amount.
- **Agent** (`agent/`, LangChain `create_agent` on OpenRouter): reaches claims
  and its instructions only through the backend's API, decides a claim, works
  out the payout when it approves, and explains the decision with the relevant
  policy section. One entry point `run(claim_id, thread_id)`.
- **Dashboard** (`dashboard/`, React + Vite + TS): the queue with each claim's
  state, each claim in full with the decision and its reasons, the agent's step
  by step work while it runs, and the agent's instructions read only.

### Claim states (from the spec)

- `waiting`: in the queue, no decision yet.
- `in_progress`: the agent is working the claim.
- `waiting_for_signoff`: the agent approved a payout over the $1,000 limit; the
  payment is blocked until a handler signs off.
- `decided`: declined, referred, or approved and payable (payout at or under
  the limit, or over the limit and signed off).

### Data note

The agent works from the policy wording alone for the pilot (`docs/SPEC.md`,
"Not for now"): no claims manual. `data/evals/` is the answer key and is never
read by the backend, the agent or this build.

---

## Phase 1: Seed the database and serve the read side

Give the backend its data and the endpoints the dashboard and agent read from.

**Builds**

- A SQLite database the backend seeds on startup from `data/`:
  `company.json`, `plans.json`, `policies.json`, `customers.json`,
  `handlers.json`, `claims.json`. Seeding is idempotent (safe to run again).
  Every claim starts in state `waiting`.
- Read endpoints, each with an `operation_id` and a one-line docstring:
  - `GET /api/claims` — the queue: for each claim the id, customer name, plan,
    claim type, amount claimed, submitted date and state.
  - `GET /api/claims/{claim_id}` — one claim in full: the story, items and
    documents, the policy and plan, the customer with claim history, and (empty
    for now) the decision and the agent's steps.
  - `GET /api/instructions` — the agent's instructions, read only.
- The agent's instructions live server-side as seed text so both the agent and
  the dashboard read the same source through the API.

**Success criteria**

- [x] `uv run pytest -q backend` passes, with tests covering: the queue lists
      all 25 claims each in state `waiting`; a claim detail returns its policy,
      plan and customer history; a missing claim id returns 404; instructions
      are returned as text.
- [x] `npm run dev:backend` then
      `curl -s http://localhost:8000/api/claims | python -m json.tool` lists 25
      claims, each with a `state` of `waiting`.
- [x] `curl -s http://localhost:8000/api/claims/CLM-1001` returns the claim with
      its items, the matching policy `POL-2001`, the `premium` plan limits, and
      the customer `Maya Patel` with her previous claim.
- [x] `curl -s http://localhost:8000/api/instructions` returns non-empty
      instruction text.
- [x] Deleting the SQLite file and restarting reseeds cleanly; a second start
      without deleting does not duplicate rows.
- [x] `npm run check:python` is green.

---

## Phase 2: Decisions and the payment guardrail

Let the backend record a decision and enforce the one hard rule about payment.

**Builds**

- `POST /api/claims/{claim_id}/decision` — records `decision`
  (`approve` | `decline` | `refer`), `payout`, `reason` and `policy_section`,
  and moves the claim to its resulting state:
  - `decline` or `refer` → `decided`, payout forced to 0.
  - `approve` with payout at or under the company approval limit → `decided`.
  - `approve` with payout over the limit → `waiting_for_signoff`.
- `POST /api/claims/{claim_id}/signoff` — a handler signs off an over-limit
  approval, clearing it for payment.
- `POST /api/claims/{claim_id}/pay` — a separate operation that takes the
  amount. It refuses (HTTP 409) to pay an amount over the limit unless the claim
  has been signed off, and refuses to pay anything but an approved claim. The
  limit comes from `company.json` (`payout_approval_limit`, $1,000).

**Success criteria**

- [x] `uv run pytest -q backend` passes, covering: recording an approve under
      the limit leaves `decided`; an approve over the limit leaves
      `waiting_for_signoff`; decline and refer leave `decided` with payout 0.
- [x] A test proves the guardrail: `pay` on an over-limit approved claim returns
      409 before sign-off, and succeeds after `signoff`. This holds even when
      the pay amount is sent directly, not just through a decision.
- [x] A test proves `pay` returns 409 for a claim that is not approved.
- [x] By API: decide `CLM-10xx` as approve with payout 2500 → detail shows
      `waiting_for_signoff`; `pay` 2500 → 409; `signoff` → 200; `pay` 2500 → 200
      and the claim reads `decided`.
- [x] `npm run check:python` is green.

---

## Phase 3: The agent decides a claim

Turn the hello-world agent into one that decides a claim through the API.

**Builds**

- The agent reads everything through backend tools only: get the claim detail,
  get its instructions. No direct file or database access.
- The system prompt is built from the server-side instructions plus the policy
  wording (`data/policy_wording.md`), which is short enough to fit the prompt.
  The agent decides approve/decline/refer, works out the payout on an approve,
  and gives a two or three sentence reason naming the relevant policy section.
- `run(claim_id, thread_id)` records the decision through
  `POST /api/claims/{claim_id}/decision` and returns the agent's final reply.
  It keeps the `llm` injection point so tests pass a stub model (no test calls a
  real model, per `docs/PROCESS.md`).
- Model config stays as in the skeleton: `openai/gpt-6-luna` at low reasoning
  effort, or `MODEL_NAME` when set.

**Success criteria**

- [x] `uv run pytest -q agent` passes with a stub model that returns a fixed
      decision: `run` posts that decision to the backend and the claim's detail
      then shows it (decision, payout, reason, policy section) and the right
      state.
- [x] A test confirms the agent's tools call the backend and that the agent is
      given no access to `data/evals/`.
- [x] A test with a stub model that approves a payout over the limit leaves the
      claim in `waiting_for_signoff` and does not pay it.
- [x] One real run (manual, not in the test suite) on `CLM-1001` with the
      default model records a sensible approve with a payout and a policy
      section, verified by reading the claim detail over the API.
- [x] `npm run check:python` is green.

---

## Phase 4: The agent's step-by-step activity

Show what the agent is doing on a claim while it works.

**Builds**

- The backend stores an ordered list of steps per claim and exposes them:
  `POST /api/claims/{claim_id}/steps` to append a step (a short label and
  detail, such as a tool call or the final decision), and the steps come back
  on the claim detail.
- `run` moves the claim to `in_progress` when it starts, appends a step as it
  reads the claim, reads instructions, and decides, then lands the claim in its
  final state when it records the decision.
- Steps are plain, readable labels in UnderCover's tone (no jargon).

**Success criteria**

- [x] `uv run pytest -q` passes, covering: a claim is `in_progress` while the
      agent works and reaches its final state at the end; steps are recorded in
      order and returned on the claim detail.
- [x] By API after a stub run: `GET /api/claims/{id}` shows a non-empty,
      ordered `steps` list ending in the decision step.
- [x] `npm run check:python` is green.

---

## Phase 5: The dashboard — queue, claim detail and instructions

Give handlers the screens the spec asks for, to UnderCover's brand.

**Builds**

- Replace the hello-world page with a small app (React + Vite + TS, strict, no
  `any`) using the brand fonts, colors and surfaces from `docs/BRAND.md`, light
  and dark:
  - **Queue**: every claim with its state shown as a labeled status (Sea Green,
    Marigold and Coral for the states), customer, type and amount.
  - **Claim detail**: the claim in full — story, items, documents, policy, plan
    and customer history — with the agent's decision, payout, reason and policy
    section when present.
  - **Instructions**: the agent's instructions from `GET /api/instructions`,
    read only.
- A small typed API client; money shown as `$1,250.00`; US spelling, short
  labels, no exclamation marks.

**Success criteria**

- [ ] `vitest run --root dashboard --coverage` passes with component tests
      (fetch stubbed) for the queue, claim detail and instructions.
- [ ] `npm run dev`, then with the Playwright MCP server: the queue page lists
      claims with their states; opening `CLM-1001` shows its story, items,
      policy and (after a run) the decision; the instructions page shows the
      text with no edit control.
- [ ] Money reads as `$1,250.00`; the page works in light and dark mode per the
      brand.
- [ ] `npm run check:ts` is green.

---

## Phase 6: Live activity view and end-to-end

Show the agent working step by step, and prove the whole pilot together.

**Builds**

- On the claim detail, an activity panel that shows the agent's steps and
  refreshes while a claim is `in_progress`, so a handler watches the work
  unfold and sees the state settle at the end.
- A Playwright end-to-end test that drives the real dashboard and backend
  against a seeded database with a pre-recorded decision and steps (no model
  call), replacing the health-only `e2e/health.spec.ts`.
- `docs/STATUS.md` updated to describe the pilot and how to run it.

**Success criteria**

- [ ] The Playwright e2e test passes: open the queue, open a claim, see its
      steps and the decision, and confirm an over-limit approve shows
      `waiting_for_signoff`.
- [ ] By hand with the Playwright MCP server: run the agent on a `waiting`
      claim and watch the detail move through `in_progress` to its final state
      with steps appearing.
- [ ] `docs/STATUS.md` reflects the pilot.
- [ ] `npm run check` is fully green (Python, TypeScript and Playwright).

---

When this plan is approved, implement it with
"Please implement the plan for the pilot" per `docs/PROCESS.md`: build each
phase in order, check every criterion, tick the boxes here, update
`docs/STATUS.md` and commit each phase.
