# PRD: CI & Containers

Phase: 16
Module codes: cross-cutting — no new B<X>/F<X> row in plan.md §6, same shape as Phases
14/15. Backend-only in the sense of "no new frontend screen"; touches CI config,
Dockerfiles, and the Makefile.

## Problem

Master-Prompt.md's Phase 16 checklist reads like CI and container tooling starts here,
but this project has had a working `.github/workflows/ci.yml` and multi-stage
Dockerfiles for both `backend/` and `frontend/` since Phase 1 (ADR 0001) — waiting
until phase 16 of 18 to add CI would have meant 15 phases of work landing with no
automated check at all, which was never realistic. Auditing both against the Phase 16
checklist item by item confirms the CI workflow already runs Postgres+pgvector,
`ruff`, `mypy`, `pytest`, frontend `tsc --noEmit` and `vite build`, and the
upgrade→downgrade→upgrade migration check; both Dockerfiles are already multi-stage,
the backend one already runs as a non-root user with a `HEALTHCHECK` against `/health`,
and the frontend one already builds via `vite build` into an `nginx` production stage
with its own `HEALTHCHECK`. This phase's real job is threefold: close three genuine
gaps the audit found (no `.dockerignore` for either image, a `make build` target
declared in the Makefile's `.PHONY` list with no recipe behind it, and no scheduled
workflow pinging `/health` — the free-tier-host-cold-start mitigation plan.md's own
risk table calls for), and record the audit itself so a future phase doesn't
re-litigate whether Phase 16's checklist is actually done.

## Actors

- **GitHub Actions**, running the new scheduled workflow against whatever production
  URL Phase 18's deploy eventually points it at — the actual actor exercising this
  phase's main new piece of automation, distinct from a human contributor.
- **A future contributor (including a future version of the assistant building later
  phases)** — `.dockerignore` and a working `make build` exist so a Docker image build
  is fast, reproducible, and locally verifiable before a deploy, not something first
  discovered to be broken during Phase 18's actual deploy attempt.

## Functional Requirements

FR-01: `backend/.dockerignore` and `frontend/.dockerignore` exclude version control,
cache/artifact directories, and environment files from the Docker build context, so
`docker build` doesn't ship or hash `.git`, `__pycache__`, `.mypy_cache`,
`.pytest_cache`, `.ruff_cache`, `.coverage`, `node_modules`, `dist`, or `.env` into
either image's build context.

FR-02: `make build` builds both production Docker images (`backend` and `frontend`
targets) locally, giving a way to verify the multi-stage Dockerfiles still produce a
working production image without deploying anywhere — currently declared in the
Makefile's `.PHONY` list with no recipe, so `make build` fails today.

FR-03: A new scheduled GitHub Actions workflow (`.github/workflows/keep-alive.yml`)
pings a configurable production `/health` URL every 10 minutes, matching plan.md's own
"Free-tier host cold starts" mitigation (Fly.io/Render/HF Spaces free tiers sleep an
idle container, which would otherwise turn a portfolio demo's first visitor of the day
into a slow cold start). Since Phase 18 hasn't deployed anywhere yet, the workflow
reads the target from a repository variable and skips gracefully — success, not
failure — when that variable is unset, the same "skip until the thing it depends on
exists" pattern `ci.yml`'s own frontend/e2e jobs already use for phases not yet built.

## User Stories

As a future contributor, I want `make build` to actually build the production images,
so a Dockerfile regression is caught locally before it's discovered during an actual
deploy.

As the person who will deploy this project in Phase 18, I want the keep-alive workflow
already built and merged, so turning it on in Phase 18 is a one-line repository
variable change, not new workflow-authoring work done under deploy-day pressure.

As anyone reviewing this project's engineering discipline, I want an explicit,
line-by-line audit record of Phase 16's checklist against what already existed, so
"CI was already there" reads as a verified, deliberate early-phase decision rather
than an unexplained gap in this phase's own work.

## Out of Scope

- Rebuilding CI's already-working ruff/mypy/pytest/tsc/build/migration-check jobs —
  the audit (see FRD) confirms every one of Phase 16's CI checklist items already
  exists and passes; touching working, already-reviewed CI config for cosmetic
  alignment with a planning doc's phase numbering isn't worth the churn, matching this
  project's own established policy from Phase 15's PRD Out of Scope section.
- Rebuilding either Dockerfile's existing multi-stage structure, non-root user, or
  `HEALTHCHECK` — all already present and correct per the audit.
- A production `docker-compose.prod.yml` — Master-Prompt.md's own Phase 18 deploy plan
  targets Fly.io/HF Spaces/Vercel/Neon directly, not a self-hosted compose stack, so
  there's no production compose file for this phase to add.
- Actually setting the keep-alive workflow's target URL, or verifying it against a
  live deployment — that's Phase 18's job, once something is actually deployed.

## Acceptance Criteria

- `docker build --target production ./backend` and `docker build --target production
  ./frontend` (via `make build`) both succeed and produce a working image, with a
  build context that excludes `.git`/cache/artifact directories.
- `.github/workflows/keep-alive.yml` is syntactically valid, runs on a 10-minute cron
  schedule, and its own logic — reading an unset repository variable and skipping
  rather than failing — is verified by actually running it once with the variable
  unset (via `workflow_dispatch`), not just read and assumed correct.
- The existing `ci.yml` and both Dockerfiles are otherwise untouched; `make test`
  (backend + frontend + e2e) still green, exactly as before this phase.
