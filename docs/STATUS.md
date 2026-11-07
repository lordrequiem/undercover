# Status

The claims pilot from `docs/PLAN.md` is built, and the harness from
`docs/HARNESS.md` and `docs/PLAN_HARNESS.md` grows it into one run that works the
whole queue on its own: a backend, an agent and a dashboard that plan a to-do
list, hand each claim to a fresh helper, look up the wording and the manual
section by section, recover from failures, and show it all on the screens.

## The harness

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
  claim is worked by `work_claim(claim_id)`, a fresh agent from a clean start
  that reports back in one line; it is also the named-claim entry point.
  `run_queue(limit)` works the whole queue: it opens a run, makes one planning
  call to order the waiting claims (capped at `limit`) into a to-do list, works
  each with a fresh helper, and finishes with a summary counting the outcomes.
  It recovers from failures on its own: `work_with_retry` tries a claim up to
  twice, a failed claim is returned to the queue between tries, and a claim that
  fails twice is left for a handler. A single guard around each claim's work
  turns any failure, including a backend outage, into a report rather than an
  escape, so one bad claim never stops the run or strands a claim in progress.
  Before finishing it re-reads the queue and works any claim the run planned
  that is still waiting. An `llm` injection point lets tests use a stub model.
  Default model `deepseek/deepseek-v4.1-flash` on OpenRouter at low reasoning
  effort, or `MODEL_NAME`.
- **Dashboard** (`dashboard/`, React + Vite + TS). To UnderCover's brand, light
  and dark: the queue with each claim's state and, alongside it, the current
  run's to-do list — each item to do, in progress, done or for a handler, with
  its note — and the run summary when finished, filling in and ticking off while
  the run works; the claim in full with the decision and the agent's activity,
  including the sections it read; and both instruction sets, read only. The
  queue and the activity panel refresh while work is in progress.

The agent looks up the policy wording and the claims manual section by section.
`data/evals/` is the answer key and is never read by the backend, the agent or
the dashboard.

## How to run

- `uv sync` and `npm install` install everything.
- `npm run dev` starts the backend and the dashboard.
- Run the whole queue, capped for a trial: `uv run python -c "from agent.main
  import run_queue; print(run_queue(limit=5))"`, then watch the queue page fill
  in and tick off. For a live run, delete `backend/undercover.db` first so the
  backend reseeds, and keep the cap at five.
- Run the agent on one named claim: `uv run python -c "from agent.main import
  work_claim; print(work_claim('CLM-1001').line)"`, then open the claim.
- `npm run check` runs every check (Python, TypeScript, Playwright). Each seed
  reloads the instruction files, so editing them takes effect on the next
  restart without deleting the database.
