# Plan for the harness

This plan grows the pilot (`docs/PLAN.md`, `docs/STATUS.md`) into the harness
the head of claims operations asks for in `docs/HARNESS.md`: one run that works
the whole queue on its own, a to-do list the team can watch, a fresh helper for
each claim, the claims manual looked up the way a handler would, automatic
recovery from failure, and readable instructions. It keeps every rule in
`docs/SPEC.md`, the tech stack in `docs/TECH_STACK.md`, and the standards in
`docs/CODE_STANDARDS.md`, and keeps every check green as `docs/PROCESS.md` asks.

The work grows in six phases, each building on the last.

## Shape of the work

Two kinds of thinking, kept apart so the risky part is testable:

- **The harness (our own code).** Deterministic orchestration that owns a run:
  it picks the waiting claims up to a cap, keeps the to-do list, hands each
  claim to a fresh helper, recovers from failure (retry once, then leave for a
  handler), never decides or pays a claim twice, never leaves a claim stuck
  `in_progress`, checks nothing in its cap was missed, and writes a short
  summary. None of this depends on a model, so every behavior is tested with a
  stub.
- **The model's judgment (LangChain `create_agent` on OpenRouter).** Used in
  exactly two places: a short **planning** call that orders the claims into the
  to-do list, and a per-claim **worker** subagent that reads what it needs,
  decides the claim and records it. Both take an `llm` injection point so tests
  pass a stub and no test calls a real model.

This is built into our own agent and backend, not a new agent framework
(`docs/HARNESS.md`, "What stays the same").

### Entry points

- `run_queue(limit=None, llm=None)` — start once, work every waiting claim (or
  the first `limit` of them), return a short summary for the handlers.
- `run(claim_id, thread_id, llm=None)` — work one named claim, as today.

### Claim states

The pilot's `waiting`, `in_progress`, `waiting_for_signoff` and `decided` stay.
One is added:

- `for_handler`: the claim failed twice and is left for a person. It has no
  recorded decision; it is not the same as a decision of `refer`.

### To-do item statuses

Each item on a run's to-do list is `to_do`, `in_progress`, `done` or
`for_handler`, mirroring `docs/HARNESS.md` req 2.

### Data note

The manual (`data/claims_manual.md`) comes into play this time, looked up
section by section rather than handed over whole. `data/evals/` stays the answer
key and is never read by the backend, the agent or the dashboard. Instructions
are written from the policy wording and the manual, never from `data/evals/`.

---

## Phase 1: Look things up — the wording and the manual

Stop handing the worker whole documents. Serve the wording and the manual as
sections it can list and read, and give it two instruction sets.

**Builds**

- The backend splits `data/policy_wording.md` and `data/claims_manual.md` into
  sections by their markdown headings and serves them, each with an
  `operation_id` and a one-line docstring:
  - `GET /api/handbook` — every section as `{section_id, document, title}`,
    in document order (`section_id` like `wording/10` or `manual/9`).
  - `GET /api/handbook/{section_id}` — one section's text, or 404.
- The per-claim worker reads through two new backend tools instead of being
  handed the wording: `list_handbook_sections()` and
  `read_handbook_section(section_id)`. Reading a section records a step
  (`Read the manual: 9. Repeat claims`), so the claim page can show what it
  read. The full wording is removed from the system prompt.
- Two instruction texts seeded server-side, written from the wording and the
  manual only: `claim_instructions` (how to work one claim, now including
  looking up the manual) and `queue_instructions` (how to run the queue).
  `GET /api/instructions` returns `{"queue": ..., "claim": ...}`.
- `docs/SPEC.md` updated so the claims manual is no longer "Not for now".

**Success criteria**

- [x] `uv run pytest -q backend` passes, covering: `GET /api/handbook` lists
      sections from both documents in order; `GET /api/handbook/{id}` returns a
      known section's text (e.g. `manual/9` contains "third claim"); an unknown
      section id returns 404; `GET /api/instructions` returns non-empty `queue`
      and `claim` text.
- [x] `uv run pytest -q agent` passes, covering: `read_handbook_section` records
      a step naming the section; `system_prompt()` (the worker's) no longer
      contains the full wording text and still contains no "evals".
- [x] By API: `curl -s http://localhost:8000/api/handbook` lists both documents'
      sections; fetching one section returns only that section.
- [x] `docs/SPEC.md` no longer lists the claims manual under "Not for now".
- [x] `npm run check:python` is green.

---

## Phase 2: A fresh helper for each claim

Turn the single-claim run into a self-contained worker a queue run can call
once per claim, and add the backend guards that stop a claim being decided or
paid twice.

**Builds**

- The worker becomes `work_claim(claim_id, llm=None)`: a fresh `create_agent`
  with a fresh thread id, built from `claim_instructions` plus the lookup tools,
  that starts the claim, decides it, and returns a one-line report —
  `CLM-1001: approve, $500.00`, `CLM-1004: refer`, or `CLM-1007: failed`. A
  clean start per claim keeps each claim's work focused and stops cost growing
  across a run. `run(claim_id, thread_id, llm=None)` stays as the named-claim
  entry point and now calls `work_claim`.
- Backend guards (`docs/HARNESS.md` req 5, "No claim is ever decided or paid
  twice"):
  - `POST /api/claims/{id}/decision` returns 409 if the claim already has a
    recorded decision.
  - `POST /api/claims/{id}/requeue` sets an `in_progress` claim back to
    `waiting`; it returns 409 on a claim that already has a decision, so a
    decided claim can never be reworked.
  - `POST /api/claims/{id}/for_handler` moves a claim (from `in_progress` or
    `waiting`) to `for_handler`.

**Success criteria**

- [x] `uv run pytest -q agent` passes, covering: `work_claim` with a stub model
      records the decision and returns a one-line report containing the claim id
      and the decision; a second `work_claim` on an already-decided claim does
      not record a second decision (the report says it is already decided).
- [x] `uv run pytest -q backend` passes, covering: a second `decision` returns
      409; `requeue` returns an `in_progress` claim to `waiting`; `requeue`
      returns 409 once a decision exists; `for_handler` moves a claim to
      `for_handler`.
- [x] By API: decide `CLM-10xx`, then `decision` again → 409; `requeue` → 409.
- [x] `npm run check:python` is green.

---

## Phase 3: One run, a to-do list and a cap

Add the run itself: pick the waiting claims up to a cap, plan them into a to-do
list, work each with a fresh helper, and finish with a summary.

**Builds**

- Backend run storage and endpoints (each with an `operation_id`):
  - `POST /api/runs` `{limit}` — opens a run over the first `limit` waiting
    claims (all of them when `limit` is null), returns its `run_id`.
  - `POST /api/runs/{run_id}/plan` `{claim_ids}` — writes the ordered to-do
    list, each item `to_do`.
  - `POST /api/runs/{run_id}/items/{claim_id}` `{status, note}` — updates one
    item (`to_do` | `in_progress` | `done` | `for_handler`) and its one-line
    note.
  - `POST /api/runs/{run_id}/finish` `{summary}` — stores the summary and marks
    the run finished.
  - `GET /api/runs/current` — the latest run: its items in order with status and
    note, and its summary when finished.
- `run_queue(limit=None, llm=None)`: opens a run, reads the capped set of
  waiting claims, makes one planning call (the injected `llm`) to order them,
  writes that order as the to-do list, then works each item in order — mark
  `in_progress`, call `work_claim`, mark `done` with the report — and finishes
  with a summary counting the outcomes. Recovery is added in Phase 4; this phase
  is the happy path.

**Success criteria**

- [x] `uv run pytest -q` passes, covering: `run_queue` with a stub model stores a
      to-do list whose items match the capped claims and end `done`;
      `GET /api/runs/current` returns them in order with their notes; the summary
      counts the outcomes.
- [x] A test proves the cap: `run_queue(limit=3)` on a fresh seed works exactly
      three claims; the other 22 stay `waiting`.
- [x] By API after a stub run: `GET /api/runs/current` shows the to-do list with
      per-item status and a summary.
- [x] `npm run check:python` is green.

---

## Phase 4: Put problems right automatically

Make a run survive timeouts, provider errors and failing steps without stopping
or stranding a claim.

**Builds**

- `work_claim` is wrapped so any failure (timeout, provider error, a failing
  step, or a worker that ends without recording a decision) is caught and
  turned into a failure report; it never escapes to stop the run.
- On a claim that failed before it was decided, the harness `requeue`s it and
  tries it once more. A second failure leaves it `for_handler`. One bad claim
  never stops the run and never leaves a claim stuck `in_progress`.
- The backend guards from Phase 2 keep any retry from deciding or paying a claim
  twice.
- Before it finishes, `run_queue` re-checks the capped set and works any claim
  still `waiting` (the missed-claims check), then writes the summary.

**Success criteria**

- [x] `uv run pytest -q` passes, covering, all with stub models:
  - [x] a worker that raises on one claim does not stop the run; the other
        claims are still worked and the run finishes.
  - [x] a claim that fails once is returned to `waiting` and tried again, and
        succeeds on the retry (its item ends `done`).
  - [x] a claim that fails twice ends `for_handler`, with the claim in state
        `for_handler` and no decision recorded.
  - [x] no claim is left `in_progress` after a run, however its worker ended.
  - [x] the missed-claims check: if a claim in the cap is still `waiting` when
        the loop ends, `run_queue` works it before finishing.
- [x] `uv run pytest -q` includes a test that a retry never records a second
      decision on a claim already decided (the Phase 2 guard, exercised through
      `run_queue`).
- [x] `npm run check:python` is green.

---

## Phase 5: The model, the dashboard and the docs

Make DeepSeek the default and show the run, the to-do list and what each claim
read on the screens, to UnderCover's brand.

**Builds**

- Default model becomes `deepseek/deepseek-v4.1-flash` on OpenRouter at low
  reasoning effort. `MODEL_NAME` still overrides it, dropping the reasoning
  effort as today.
- Dashboard (React + Vite + TS, strict, no `any`, brand per `docs/BRAND.md`,
  light and dark):
  - **Queue page**: alongside the claims and their states, the current run's
    to-do list — each item with its claim, status (`to_do`, `in_progress`,
    `done`, `for_handler`) and one-line note — and the run summary when
    finished. The page refreshes while the run is working, so the list fills in
    and is ticked off as it goes.
  - **Claim page**: the steps already show the agent's work; confirm the lookup
    steps (the sections it read) appear there. A `for_handler` claim shows that
    state.
  - **Instructions page**: both instruction sets (queue and claim) from
    `GET /api/instructions`, read only.
  - A new `for_handler` status color added to `StatusBadge` within the brand.
- `docs/STATUS.md`, `docs/TECH_STACK.md` and `docs/SPEC.md` updated to describe
  the product as it now is.

**Success criteria**

- [x] `uv run pytest -q agent` passes a test that the default model is
      `deepseek/deepseek-v4.1-flash` and that `MODEL_NAME` overrides it.
- [x] `vitest run --root dashboard --coverage` passes with component tests
      (fetch stubbed) for the to-do list on the queue page (the four statuses
      and the summary), the `for_handler` badge, and the instructions page
      showing both sets.
- [x] `npm run dev`, then with the Playwright MCP server: the instructions page
      shows both instruction sets with no edit control; a claim worked by a stub
      shows its read-the-manual steps.
- [x] `docs/STATUS.md`, `docs/TECH_STACK.md` and `docs/SPEC.md` describe the
      harness, the default model, the manual and the run.
- [x] `npm run check:ts` is green.

---

## Phase 6: A whole run, end to end

Prove the harness runs the queue on its own against the real model, and that the
screens show it.

**Builds**

- A Playwright end-to-end test that drives the dashboard and backend against a
  seeded database with a pre-recorded run (a to-do list, per-item statuses and
  steps, no model call): the queue page shows the to-do list filling and being
  ticked off and the summary, and a claim shows its steps including the sections
  read.
- `docs/STATUS.md` finalized for the harness and how to run it.

**Success criteria**

- [x] The Playwright e2e test passes: open the queue, see the run's to-do list
      with mixed statuses and the summary, open a claim and see its steps
      including a section it read, and confirm a `for_handler` claim shows that
      state.
- [ ] By hand, with a real run: delete `backend/undercover.db`, start the
      backend so it reseeds, then
      `uv run python -c "from agent.main import run_queue; print(run_queue(limit=5))"`.
      Five claims are worked on their own; the dashboard queue shows the to-do
      list fill in and tick off and each claim's steps including the sections it
      read; the other 20 claims stay `waiting`; the printed summary matches.
      (Left for a run on the real model, which spends OpenRouter credits.)
- [x] `npm run check` is fully green (Python, TypeScript and Playwright).

---

When this plan is approved, implement it with "Please implement the plan for the
harness" per `docs/PROCESS.md`: build each phase in order, check every
criterion, tick the boxes here, update `docs/STATUS.md`, and commit each phase.
For any live run with the real model, reseed first and cap the run at five
claims.
