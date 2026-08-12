# NFR: Foundation

## Performance

- `GET /health` does one `SELECT 1` over the pooled connection and returns; no
  external calls (never touches an LLM provider). Target: sub-50ms locally.
- The async engine uses `pool_pre_ping=True` so a stale pooled connection is
  detected and replaced rather than surfacing as a request failure.
- No caching in this phase — nothing here is expensive enough to warrant it yet.
  `semantic_cache` (the table) exists for Phase 6+'s LLM-response caching, but
  nothing reads/writes it yet.
- All handlers and DB access in this phase are `async def`; nothing blocks the
  event loop (no sync DB driver, no sync `requests` calls).

## Security

- Passwords: argon2id via `argon2-cffi`, never a faster/weaker hash.
- Access tokens: JWT (HS256), secret from `Settings.jwt_secret` (required, no
  default — the app refuses to boot without it), 15-minute default TTL.
- Refresh tokens: opaque `secrets.token_urlsafe(48)` values; only their SHA-256
  hash is ever persisted (`refresh_tokens.token_hash`), so a DB read (or leak)
  cannot be replayed as a valid token.
- Tenant isolation: every workspace-scoped table has a `workspace_id` FK with
  `ondelete="CASCADE"`; `get_current_workspace` is the single enforcement point
  every future route depends on, and it returns 404 (not 403) for a workspace the
  caller isn't a member of, so probing for other tenants' workspace IDs doesn't
  even confirm existence.
- Secrets: `.env` is gitignored (`!.env.example` is the only tracked env file);
  no API key, model ID, or secret is hardcoded anywhere in this phase's code —
  confirmed by grep during review.
- CORS is restricted to `Settings.cors_origins_list` (comma-separated env var),
  not a wildcard.

## Reliability

- `GET /health` degrades gracefully: any exception from the DB probe is caught
  and reported as `db_connected: false` / `status: "degraded"`, never a 500 or an
  unhandled exception.
- The app boots and serves traffic with zero LLM keys configured — nothing in
  this phase's code path can fail due to an absent `llm_api_key`/`groq_api_key`.
- `dispose_engine()` runs on shutdown so connections aren't leaked across
  reloads (relevant under `uvicorn --reload` in the dev container).

## Observability

- All logs are structured JSON via `structlog` (`app/core/logging.py`), routed
  through stdlib `logging` at `INFO` level.
- `RequestIDMiddleware` generates or forwards `X-Request-ID`, binds it into
  `structlog`'s contextvars for the life of the request, and echoes it back in
  the response header — every log line emitted while handling a request carries
  that ID.
- `app_startup` (with `llm_configured`) and `app_shutdown` are logged once per
  process lifecycle.
- No metrics/tracing endpoint yet — that's B15 (`observability`), Phase 13.

## Testability

- Backend: `backend/tests/test_security.py` and `test_pagination.py` unit-test
  `app/core/security.py`'s functions (hash/verify, refresh-token generation/hashing,
  access-token roundtrip and expiry) and `app/core/pagination.py`'s cursor
  encode/decode — all pure, no DB needed. `backend/tests/test_health.py`
  integration-tests `GET /health` end-to-end through the real ASGI app via
  `httpx.ASGITransport`, covering both the DB-reachable and DB-unreachable
  branches (the latter by monkeypatching the engine). `app/core/deps.py`'s
  dependencies (`get_current_user`/`get_current_workspace`/`require_role`) aren't
  unit tested yet since they need a real `User`/`WorkspaceMember` row to query —
  Phase 2 (auth) adds that coverage alongside its own routes, once those rows can
  actually be created through the API.
- Frontend: none — no frontend code exists yet (Phase 3).
- E2E: deferred — no user-facing journey exists yet, and the isolated Playwright
  stack (`docker-compose.test.yml`) depends on `app.seed.seed` (Phase 11) and
  `frontend/package.json` (Phase 3), neither of which exist. `GET /health` was
  verified both manually via `curl` and by `test_health.py`; see
  `docs/decisions/0001-phase-1-foundation.md` §4 for the full reasoning.

## Constraints

- Python 3.11+ at runtime (`pyproject.toml` `requires-python`, `backend/Dockerfile`
  base image `python:3.11-slim`). `mypy.ini`'s `python_version` is pinned to 3.12
  for type-checking only, to work around installed `numpy`'s stubs using PEP 695
  syntax unconditionally — this does not change the runtime target; see
  `docs/progress.md` for the full explanation.
- Async throughout: SQLAlchemy 2.0 async engine, `asyncpg` driver, async FastAPI
  handlers. No sync DB access anywhere in this module.
- Pydantic v2 (`Settings`, `CursorPage`) at every boundary that has one yet.
- One database: PostgreSQL 16 + pgvector. No Neo4j, no Chroma, no Redis.
- Migrations only: the schema was created by `alembic revision --autogenerate` +
  manual review, never `Base.metadata.create_all()`.
- Zero paid services: embeddings run locally via `sentence-transformers`; the app
  fully functions with no LLM key at all.
- `mypy app --strict` and `ruff check .` must both be clean — enforced in this
  phase and going forward.
