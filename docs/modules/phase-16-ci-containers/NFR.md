# NFR: CI & Containers

## Performance

- `.dockerignore` for both images reduces build-context size and, for the frontend
  image specifically, avoids hashing a potentially-large local `node_modules/` into
  Docker's build-cache key — a real, if modest, build-time win, not just hygiene.
- The keep-alive workflow's own runtime cost is trivial (`curl` against one URL every
  10 minutes) and runs on GitHub's free Actions minutes for a public/private repo at
  this project's scale — not a resource concern.

## Security

- The keep-alive workflow's target is a repository *variable*, not a *secret*,
  deliberately — a health-check URL for a portfolio demo isn't sensitive information,
  and using a variable (visible in workflow logs and the Actions UI) rather than a
  secret makes the workflow's own behavior easier to debug without weakening anything
  real. If a future phase's deployed URL ever needed to stay private, that would be a
  reason to reconsider — not the case here.
- `.dockerignore` excluding `.env` from both build contexts is itself a security
  property, not just a build-time optimization — without it, a local `.env` (if one
  happened to exist in the build directory when `docker build` ran without
  `--no-cache`-style caution) could be copied into an image layer and ship real
  secrets in a container image. Neither Dockerfile's `COPY . .` step should ever be
  able to reach `.env` at all now.

## Reliability

- The keep-alive workflow deliberately has no retry logic (see FRD Edge Cases) — its
  job is generating periodic real traffic against a free-tier host to prevent
  idle-sleep, not uptime monitoring with alerting semantics; a single missed tick
  failing loudly (rather than being silently retried into a false green) is the
  correct behavior for what this workflow is actually for.
- Skip-gracefully-until-the-dependency-exists (FR-03, the unset-`HEALTH_CHECK_URL`
  path) keeps the repository's overall Actions status green between now and Phase 18,
  the same reliability property `ci.yml`'s own frontend/e2e jobs already established
  for pre-Phase-3/pre-Phase-11 states — a scheduled workflow that fails on every tick
  starting the moment it's merged, for reasons unrelated to any real problem, would
  train "check the Actions tab" into "ignore the Actions tab," which defeats its
  purpose for the one time it should actually alarm someone.

## Testability

- FR-03's skip path is verified by actually running the workflow via
  `workflow_dispatch` with the variable unset (PRD Acceptance Criteria), not just
  read and assumed correct — the same "verify empirically, don't assume" discipline
  this project has applied since Phase 14's FastAPI route-traversal verification and
  Phase 15's dependency-resolution-order check.
- `make build`'s new recipe is itself the test for both Dockerfiles' `production`
  stages — a broken production build is now caught by running one Makefile target
  locally, rather than first discovered during Phase 18's actual deploy.

## Constraints

- No new database table/column, no new API route, no new frontend code — this phase
  changes zero application runtime behavior; every change is either build/CI
  configuration or a new, independent scheduled workflow.
- `keep-alive.yml` is additive — a new workflow file, not a change to `ci.yml`'s
  existing jobs, matching this project's established preference (Phase 15 FRD) for
  extending or adding an isolated gate over modifying a working one.
- Async/type-hint/mypy-strict constraints don't apply here — no Python or TypeScript
  application code changes this phase.
