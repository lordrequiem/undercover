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

## In progress

- Phase 2 onward: decisions and the payment guardrail, the agent, the
  dashboard and the end-to-end test.

## How to run

- `npm run dev` starts the backend and the dashboard.
- `npm run check` runs every check (Python, TypeScript, Playwright).
