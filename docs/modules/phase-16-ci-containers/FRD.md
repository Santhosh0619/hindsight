# FRD: CI & Containers

## API Endpoints (Backend — FastAPI)

None new. `/health` (added Phase 1) is reused as the keep-alive workflow's target.

## React Components (Frontend)

None. No new frontend code this phase.

## Data Model Changes

None.

## The audit — Phase 16's checklist vs. what already exists

Confirmed line-by-line against Master-Prompt.md's Phase 16 section:

| Checklist item | Status | Where |
|---|---|---|
| Postgres+pgvector service container in CI | Already exists | `.github/workflows/ci.yml` `backend` and `migrations` jobs, `pgvector/pgvector:pg16` |
| `ruff`, `mypy`, `pytest` | Already exists | `ci.yml` `backend` job |
| Frontend `tsc --noEmit` and `vite build` | Already exists | `ci.yml` `frontend` job (also runs `prettier --check`, not required by the checklist but already present) |
| Migration check (`upgrade head` → `downgrade base` → `upgrade head`) | Already exists | `ci.yml` `migrations` job |
| Multi-stage backend Dockerfile, non-root, healthcheck | Already exists | `backend/Dockerfile` — `base`/`deps`/`development`/`production` stages, `USER appuser`, `HEALTHCHECK` against `/health` |
| Multi-stage frontend Dockerfile, build → nginx | Already exists | `frontend/Dockerfile` — `base`/`deps`/`development`/`builder`/`production` stages, `nginx:alpine` final stage, `HEALTHCHECK` |
| Cron workflow pinging `/health` every 10 minutes | **Missing** | Added this phase — see below |

All CI jobs and both Dockerfiles were built in Phase 1 (ADR 0001) out of necessity —
15 phases of work landing with zero automated check between them was never a realistic
option — so this phase's CI/Dockerfile checklist items are audit-and-confirm, not
build-from-scratch. Two smaller gaps the audit found beyond the missing cron workflow:
no `.dockerignore` for either image, and a `make build` target declared in the
Makefile's `.PHONY` list with no recipe behind it (`make build` currently fails with
"No rule to make target").

### `backend/.dockerignore`, `frontend/.dockerignore` (new)

- Backend excludes: `.git`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/`,
  `.ruff_cache/`, `.coverage`, `*.egg-info/`, `.env`, `*.log`.
- Frontend excludes: `.git`, `node_modules/`, `dist/`, `.env`, `*.log`.
- `node_modules`/dependency-install output is excluded even though the `deps` stage
  reinstalls it fresh via `npm ci`/`pip install` — a stale local `node_modules` in the
  build context otherwise gets hashed into Docker's layer-cache key unnecessarily
  (slower, and can mask a `package-lock.json` change that should have invalidated the
  cache) even though its *contents* are never copied into a stage that matters.

### `Makefile` — `build` target given a real recipe

- `docker build --target production -t hindsight-backend:local ./backend` and the
  frontend equivalent, run sequentially. Local-only verification that both
  `production` stages still build cleanly — not used by CI (which doesn't build
  images at all yet; that's Phase 18's deploy step) and not a new CI job, just closing
  a `.PHONY` declaration that had no matching recipe.

### `.github/workflows/keep-alive.yml` (new)

- Triggers: `schedule` (`*/10 * * * *`, matching plan.md's "every 10 minutes") and
  `workflow_dispatch`, so it can be run on demand to verify its own logic without
  waiting up to 10 minutes for the next scheduled tick.
- Reads the target URL from `vars.HEALTH_CHECK_URL` (a repository variable, not a
  secret — a health-check URL isn't sensitive, and repository variables show up
  directly in the Actions UI/logs, which secrets deliberately don't, making this
  workflow's behavior easier to debug). Set to empty by default (unset) until Phase 18
  deploys somewhere.
- If unset, the job logs a message and exits `0` (success) — matching `ci.yml`'s own
  established pattern (`frontend`/`e2e` jobs' `steps.check.outputs.exists` gate) for
  "the thing this depends on doesn't exist yet, skip without failing the workflow run
  or the repo's overall Actions status."
- If set, `curl -f --max-time 10` against `${{ vars.HEALTH_CHECK_URL }}` — a non-2xx
  response or timeout fails the job, which surfaces as a red workflow run (this
  project has no on-call/paging setup, so a visibly failed scheduled run in the
  Actions tab is the entire alerting mechanism, appropriate for a portfolio project's
  actual operational stakes).

## Dependencies

- Calls: the deployed app's own `/health` endpoint (Phase 1) — no new endpoint.
- Called by: nothing — this is leaf infrastructure, not depended on by any other
  module.

## Sequence Flows

### Keep-alive tick, variable set

1. GitHub Actions cron fires every 10 minutes.
2. Job reads `vars.HEALTH_CHECK_URL`; it's non-empty.
3. `curl -f --max-time 10 "$HEALTH_CHECK_URL"`.
4. 2xx within 10s → job succeeds, container's free-tier host sees real traffic and
   stays warm.
5. Non-2xx or timeout → job fails, visible as a red run in the Actions tab.

### Keep-alive tick, variable unset (current state, until Phase 18)

1. GitHub Actions cron fires every 10 minutes.
2. Job reads `vars.HEALTH_CHECK_URL`; it's empty.
3. Job logs "HEALTH_CHECK_URL not set, nothing to ping yet" and exits 0.

## Edge Cases & Error Handling

- **The workflow runs before Phase 18 ever deploys anything**: handled by the
  unset-variable skip path above — verified by actually triggering the workflow via
  `workflow_dispatch` with the variable unset, not just read and assumed correct (see
  PRD Acceptance Criteria).
- **A transient network blip fails one tick**: no retry logic added — a single missed
  10-minute tick failing loudly is the correct behavior for this workflow's actual
  job (which is generating periodic traffic to prevent idle-sleep, not monitoring
  uptime with alerting semantics); a real outage shows up as several consecutive red
  runs, which is enough signal for a portfolio project with no paging setup.
