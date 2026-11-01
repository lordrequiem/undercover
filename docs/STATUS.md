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

## In progress

- Phase 3 onward: the agent, its activity steps, the dashboard and the
  end-to-end test.

## How to run

- `npm run dev` starts the backend and the dashboard.
- `npm run check` runs every check (Python, TypeScript, Playwright).
