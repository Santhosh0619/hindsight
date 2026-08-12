# PRD: Foundation
Phase: 1
Module codes: B1 (`core`), B2 (`db`) — plus the initial schema underlying every later
backend module (B3–B17) from plan.md §6/§8

Note: written retroactively. The backend for this phase was implemented before this
document — see `docs/progress.md` for how that gap happened and what was verified
against the running code before this doc was written.

## Problem

Every later phase (auth, catalog, ingestion, retrieval, the agent pipeline, evaluation)
needs a running, typed, async backend wired to Postgres+pgvector, plus the cross-cutting
plumbing (config, password/token primitives, error handling, structured logging,
pagination) and the complete data model for the whole product. Without this in place
first, every later phase would repeatedly touch foundational infrastructure instead of
adding pure business logic against an already-migrated schema.

## Actors

- Backend developer, extending the modules built on top of this one.
- The FastAPI app itself, at process boot (`lifespan`) and per-request.
- CI (`make lint`, `make typecheck`, `make test`), which runs against this module on
  every push.
- Every future request handler and background worker, which depends on `app.core.*`
  and `app.db.*` rather than reimplementing config/auth/session handling.

## Functional Requirements

FR-01: Application configuration loads from the environment / `.env` into a single
typed `Settings` object (`app/core/config.py`); a missing required secret (e.g.
`jwt_secret`) fails at startup, not at first use.

FR-02: Passwords are hashed with argon2id (`app/core/security.py`); JWT access tokens
are issued and decoded with a configurable TTL; refresh tokens are opaque random
strings, stored and compared only as their SHA-256 hash — the raw token is never
persisted.

FR-03: A set of FastAPI dependencies (`app/core/deps.py`) resolves the current user
from a `Bearer` access token, the current workspace membership from a `workspace_id`,
and gates endpoints to a given set of `WorkspaceRole`s via `require_role(*roles)`.

FR-04: Typed application exceptions (`AppError` and its subclasses in
`app/core/errors.py`) render as a single consistent JSON envelope
`{"error": {"code", "message", "detail"}}` with the matching HTTP status, via a
FastAPI exception handler.

FR-05: List endpoints can paginate through an opaque, base64-encoded cursor over
`(created_at, id)` (`app/core/pagination.py`).

FR-06: All application logs are structured JSON (`structlog`), and every HTTP request
is tagged with a request ID injected by `RequestIDMiddleware` (`app/core/logging.py`).

FR-07: The async SQLAlchemy engine and session factory (`app/db/session.py`) are
created lazily on first use and disposed on shutdown; the Postgres `vector` extension
is ensured to exist at startup (`app/db/init.py`).

FR-08: Every table required by later phases exists as a single initial Alembic
migration — users/auth, workspaces/membership/audit/API-keys, service catalog and
graph edges, postmortems and their chunks/facts/failure-modes, incidents/briefs/
feedback, agent runs and steps, the job queue, the evaluation harness's cases/runs/
results, and the semantic cache. Every workspace-scoped table has a `workspace_id`
foreign key with `ondelete="CASCADE"` and an index on it (plan.md §8).

FR-09: `GET /health` reports the API version, live DB connectivity (`SELECT 1`), and
whether an LLM provider key is configured — all without requiring an LLM key to be
present, and without ever raising even if the DB is down.

## User Stories

- As a backend developer, I want a single typed `Settings` object, so that I never
  grep `.env` files or scatter `os.environ` calls across modules.
- As a future endpoint author, I want `get_current_user` / `get_current_workspace` /
  `require_role` dependencies, so that auth and tenancy checks are declared once and
  enforced identically everywhere they're used in Phase 2 onward.
- As an operator, I want `GET /health` to report DB connectivity and LLM key presence,
  so that I can verify a deploy without ever calling out to an LLM provider.
- As the author of any later backend module, I want its tables already migrated by
  this phase, so that phase only ever adds service/route code, never schema chasing.

## Out of Scope

- Any HTTP route beyond `GET /health` (signup/login/workspaces/etc. are Phase 2).
- Business-logic services for any domain table (catalog, ingestion, retrieval,
  agents, evaluation) — this phase only creates the tables and the shared plumbing.
- The frontend (Phase 3) and the background worker process's actual job-processing
  loop (Phase 5) — their Docker Compose services exist but are not started until
  their own phase lands real code.
- Any LLM call, embedding computation, or retrieval logic — `EmbeddingVector` exists
  as a column type only; nothing populates or queries it yet.

## Acceptance Criteria

Per Master-Prompt.md's Phase 1 checkpoint:

1. `docker compose up -d db api` (the two services with real code so far) starts
   cleanly; `worker`/`web` come online in Phase 5/Phase 3 respectively.
2. `alembic upgrade head` applies the initial migration with zero errors against a
   freshly created database, and `alembic check` reports no drift against the models.
3. `GET /health` returns `200` with `status`, `version`, `db_connected`, and
   `llm_configured` in the response body.
4. `ruff check .` and `mypy app --strict` both report zero errors.
