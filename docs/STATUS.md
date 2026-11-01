# Status

Building the claims pilot from `docs/PLAN.md`.

## Done

- **Phase 1 — seed and read side.** The backend seeds a SQLite database on
  startup from `data/` (idempotently) and serves the read side:
  - `GET /api/claims` — the queue, every claim in state `waiting`.
  - `GET /api/claims/{claim_id}` — one claim in full with its policy, plan,
    customer history, and (empty for now) decision and steps.
  - `GET /api/instructions` — the agent's instructions, read only, seeded from
    `backend/instructions.md`.
- **Phase 2 — decisions and the payment guardrail.**
  - `POST /api/claims/{claim_id}/decision` records a decision (approve, decline
    or refer) and moves the claim to `decided` or, for an over-limit approve, to
    `waiting_for_signoff`.
  - `POST /api/claims/{claim_id}/signoff` clears an over-limit approval.
  - `POST /api/claims/{claim_id}/pay` takes an amount and refuses (409) to pay
    over the $1,000 limit until the claim is signed off, or to pay a claim that
    is not approved.
- **Phase 3 — the agent decides a claim.** The agent reaches the claim and its
  instructions only through the backend API. Its system prompt is the
  server-side instructions plus the policy wording; it reads the claim with
  `get_claim`, decides, and records the decision with `submit_decision`. One
  entry point, `run(claim_id, thread_id)`, with an `llm` injection point so
  tests pass a stub model. The default model is `openai/gpt-6-luna`.
- **Phase 4 — the agent's step-by-step activity.** The backend stores an ordered
  list of steps per claim (`POST /api/claims/{claim_id}/start` and
  `POST /api/claims/{claim_id}/steps`), returned on the claim detail. `run`
  marks the claim `in_progress`, records a step as it picks up the claim, reads
  the instructions, reads the claim and records the decision, then lands the
  claim in its final state.

## In progress

- Phase 5 onward: the dashboard and the end-to-end test.

## How to run

- `npm run dev` starts the backend and the dashboard.
- `npm run check` runs every check (Python, TypeScript, Playwright).
