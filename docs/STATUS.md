# Status

The claims pilot from `docs/PLAN.md` is built: a backend, an agent and a
dashboard that work the claims queue the way a handler does.

## The pilot

- **Backend** (`backend/`, FastAPI + SQLite). Seeds a database on startup from
  `data/` (idempotently) and serves the queue, the claim detail, the agent's
  instructions (read only) and the agent's activity. It records decisions and
  owns the one guardrail: no payment over the $1,000 limit until a handler signs
  off, and only on an approved claim. It also serves the policy wording and the
  claims manual section by section, so the agent looks them up rather than being
  handed whole documents.
  - `GET /api/claims`, `GET /api/claims/{id}`, `GET /api/instructions`
    (the queue and claim instruction sets)
  - `GET /api/handbook`, `GET /api/handbook/{section_id}`
  - `POST /api/claims/{id}/start`, `POST /api/claims/{id}/steps`
  - `POST /api/claims/{id}/decision`, `.../signoff`, `.../pay`
  - `POST /api/claims/{id}/requeue`, `.../for_handler`
  - `POST /api/runs`, `.../plan`, `.../items/{claim_id}`, `.../finish`,
    `GET /api/runs/current` for the current run and its to-do list
  - No claim is decided twice: a second decision, or a requeue of a decided
    claim, is refused with 409.
- **Agent** (`agent/`, LangChain `create_agent` on OpenRouter). Reaches the
  claim and its instructions only through the backend API. Its prompt is the
  server-side claim instructions; it reads the claim, looks up the sections of
  the wording and the manual it needs, decides approve, decline or refer, works
  out the payout, and records the decision with the relevant policy section. A
  claim is worked by `work_claim(claim_id)`, a fresh agent with a fresh thread
  that reports back in one line; `run(claim_id, thread_id)` is the named-claim
  entry point and calls it. `run_queue(limit)` works the whole queue: it opens a
  run, makes one planning call to order the waiting claims (capped at `limit`)
  into a to-do list, works each with a fresh helper, and finishes with a summary
  counting the outcomes. It recovers from failures on its own: a failed claim is
  caught, returned to the queue and tried once more, and a claim that fails
  twice is left for a handler, so one bad claim never stops the run or strands a
  claim in progress. Before finishing it re-checks that no capped claim is still
  waiting. An `llm` injection point lets tests use a stub model. Default model
  `openai/gpt-6-luna`, or `MODEL_NAME`.
- **Dashboard** (`dashboard/`, React + Vite + TS). To UnderCover's brand, light
  and dark: the queue with each claim's state, the claim in full with the
  decision and the agent's activity, and the instructions read only. The
  activity panel refreshes while a claim is in progress.

The agent works from the policy wording alone. `data/evals/` is the answer key
and is never read by the backend, the agent or the dashboard.

## How to run

- `uv sync` and `npm install` install everything.
- `npm run dev` starts the backend and the dashboard.
- Run the agent on a claim: `uv run python -c "from agent.main import run;
  print(run('CLM-1001', 'session-1'))"`, then open the claim in the dashboard.
- `npm run check` runs every check (Python, TypeScript, Playwright).
