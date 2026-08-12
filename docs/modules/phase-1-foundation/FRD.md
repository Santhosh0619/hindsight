# FRD: Foundation

## API Endpoints (Backend — FastAPI)

### `GET /health`
- Auth required: no
- Request schema: none
- Response schema (plain `dict[str, object]`, no request body to validate):
  ```json
  {
    "status": "ok" | "degraded",
    "version": "0.1.0",
    "db_connected": true,
    "llm_configured": true
  }
  ```
  `status` is `"degraded"` (not an error response) when `db_connected` is `false` —
  the endpoint always returns `200` so uptime checks don't need special-case handling
  for "the DB is briefly unreachable."
- Error codes: none — the handler catches any exception from the DB probe and
  reports `db_connected: false` instead of propagating.

No other routes exist yet. `app_error_handler` is registered against `AppError` for
every future route to reuse.

## React Components (Frontend)

None. The frontend module (`frontend/Dockerfile`, `nginx.conf`, `tsconfig.json`) is
scaffolded but has no `package.json`/source yet — that's Phase 3.

## Data Model Changes

One Alembic revision (`b9e49c30b2c7_initial_schema.py`), 27 tables, matching
plan.md §8. `UUIDPrimaryKeyMixin` (uuid4 PK) and `TimestampMixin`
(`created_at`, server-side `now()`) are applied where plan.md calls for them.

**Auth / users** (B3 data layer)
- `users` — email (unique, indexed), password_hash, full_name, is_active, is_demo.
- `refresh_tokens` — user_id → users (CASCADE), token_hash (unique, indexed),
  expires_at, revoked_at, user_agent.

**Workspaces / tenancy** (B4 data layer)
- `workspaces` — name, slug (unique, indexed), is_demo.
- `workspace_members` — composite PK (workspace_id, user_id), role
  (`workspace_role` enum: owner/responder/viewer).
- `api_keys` — workspace_id → workspaces (CASCADE), name, key_hash (unique,
  indexed), prefix, created_by → users (SET NULL), last_used_at, revoked_at.
- `audit_log` — workspace_id → workspaces (CASCADE), actor_user_id → users
  (SET NULL), action, target_type, target_id, meta (JSONB).

**Service catalog / graph** (B5/B6 data layer)
- `teams` — workspace_id → workspaces (CASCADE), name, slack_handle,
  escalation_contact.
- `services` — workspace_id → workspaces (CASCADE), name (unique per workspace),
  tier (`service_tier` enum: TIER_1/TIER_2/TIER_3 — an `int`-valued enum, so its DB
  labels are the member *names*, not lowercase values; see Internal Architecture),
  team_id → teams (SET NULL), repo_url, description, runbook_url.
- `service_edges` — workspace_id → workspaces (CASCADE), from/to_service_id →
  services (CASCADE), kind (`edge_kind` enum: calls/reads_from/publishes_to/
  depends_on), criticality (`edge_criticality` enum: hard/soft), unique on
  (from, to, kind).

**Postmortems / knowledge base** (B7/B8 data layer)
- `postmortems` — workspace_id → workspaces (CASCADE), external_ref, title,
  occurred_at, duration_minutes, severity (`severity` enum: sev1–sev4), raw_text,
  redacted_text, status (`postmortem_status` enum: pending/processing/indexed/
  failed), failure_reason, injection_flagged, created_by → users (SET NULL).
  Composite index on (workspace_id, status).
- `postmortem_chunks` — postmortem_id → postmortems (CASCADE), chunk_index,
  section_label, content, char_start/end, `embedding` (pgvector `VECTOR(384)`,
  nullable until the ingestion pipeline populates it), `tsv` (Postgres
  `TSVECTOR`, nullable). Indexes: HNSW on `embedding` (`m=16, ef_construction=64,
  vector_cosine_ops` — Phase 0 verified HNSW availability on the installed
  pgvector version), GIN on `tsv` for full-text search.
- `failure_modes` — workspace_id → workspaces (CASCADE), label (unique per
  workspace), canonical_description, category.
- `postmortem_facts` — postmortem_id → postmortems (CASCADE), fact_type
  (`fact_type` enum: trigger/root_cause/remediation/detection_gap/
  contributing_factor), statement, confidence, source_chunk_id →
  postmortem_chunks (CASCADE).
- `postmortem_services` (join) — (postmortem_id, service_id, role) composite PK,
  role (`service_link_role` enum: root_cause/affected/downstream), confidence.
- `postmortem_failure_modes` (join) — (postmortem_id, failure_mode_id) composite
  PK, confidence.

**Incidents / briefs** (B10/B11 data layer)
- `incidents` — workspace_id → workspaces (CASCADE), external_ref, title,
  raw_alert_text, severity (plain string, not an enum — free text from whatever
  alerting system posts it), status (`incident_status` enum: open/mitigated/
  resolved/false_positive), opened_by → users (SET NULL), opened_at, resolved_at.
  Composite index on (workspace_id, status).
- `incident_signals` — incident_id → incidents (CASCADE), symptoms (JSONB),
  error_strings (text array), metrics (JSONB), affected_service_ids (UUID array),
  time_window (JSONB), extracted_by_model, extraction_confidence.
- `briefs` — incident_id → incidents (CASCADE), version, status (`brief_status`
  enum: generating/ready/failed), hypotheses/matched_postmortems/blast_radius/
  runbook_steps/page_list/citations (all JSONB), overall_confidence,
  correction_passes, llm_used, from_cache, generated_at.
- `brief_feedback` — brief_id → briefs (CASCADE), user_id → users (SET NULL),
  verdict (`feedback_verdict` enum: helpful/partially/unhelpful),
  correct_postmortem_id → postmortems (SET NULL), note.
- `agent_runs` — incident_id → incidents (CASCADE), graph_version, status (plain
  string — the LangGraph node/edge state names aren't fixed yet), started_at,
  finished_at, total_tokens_in/out, error.
- `agent_run_steps` — run_id → agent_runs (CASCADE), seq, node_name, status,
  latency_ms, tokens_in/out, input_summary/output_summary (JSONB), error.

**Jobs** (B13 data layer)
- `jobs` — workspace_id → workspaces (CASCADE), kind, payload (JSONB), status
  (`job_status` enum: queued/running/done/failed/dead), attempts, max_attempts,
  run_after, locked_by, locked_at, last_error. Partial index
  `ix_jobs_claim_queue` on (status, run_after) `WHERE status = 'queued'`, so the
  worker's claim query stays cheap as the table fills with done/dead rows.

**Evaluation** (B14 data layer)
- `eval_cases` — workspace_id → workspaces (CASCADE), name, incident_text,
  expected_postmortem_ids/expected_service_ids (UUID arrays), notes.
- `eval_runs` — workspace_id → workspaces (CASCADE), git_sha, started_at,
  finished_at, recall_at_1/recall_at_5/mrr/groundedness/citation_validity,
  cases_run, notes.
- `eval_case_results` — eval_run_id → eval_runs (CASCADE), eval_case_id →
  eval_cases (CASCADE), retrieved_ids (UUID array), rank_of_first_hit,
  groundedness, passed.

**System**
- `semantic_cache` — workspace_id → workspaces (CASCADE), purpose, prompt_hash
  (indexed), `embedding` (pgvector `VECTOR(384)`, nullable), response (JSONB),
  model, hits.
- `alembic_version` — Alembic's own bookkeeping table.

## Internal Architecture

- `app/core/config.py` — `Settings(BaseSettings)`, `get_settings()` (`lru_cache`d
  singleton). Every optional LLM-related field defaults to `None`/a placeholder so
  the app boots with zero external keys; `llm_configured` is a derived property
  (`bool(llm_api_key)`), not a stored setting.
- `app/core/security.py` — pure functions: `hash_password`/`verify_password`
  (argon2id via the `argon2` package), `generate_refresh_token`/
  `hash_refresh_token` (opaque token + SHA-256, so a stolen row hash can't be
  turned back into a usable token), `create_access_token`/`decode_access_token`
  (PyJWT, HS256, secret from `Settings`).
- `app/core/deps.py` — `get_db` (re-exported from `app.db.session`),
  `get_current_user` (Bearer token → `User`, 401 on anything wrong), `get_current_
  workspace` (→ `WorkspaceMember`, 404 — not 403 — when the caller isn't a member,
  so a request for someone else's workspace doesn't leak that it exists),
  `require_role(*roles)` (dependency factory → 403 if the member's role isn't in
  the allowed set).
- `app/core/errors.py` — `AppError` base + `NotFoundError`/`UnauthorizedError`/
  `ForbiddenError`/`ConflictError`/`ValidationAppError`/`LLMUnavailableError`,
  each a `(status_code, code)` pair; `app_error_handler` renders the JSON envelope.
- `app/core/pagination.py` — `CursorPage[T]` envelope, `encode_cursor`/
  `decode_cursor` over `(created_at, id)`, base64url-encoded.
- `app/core/logging.py` — `configure_logging()` wires `structlog` to JSON output
  via stdlib logging; `RequestIDMiddleware` reads/generates `X-Request-ID`, binds
  it into `structlog`'s contextvars for the duration of the request, and echoes it
  back in the response header; `get_logger(name)` returns a
  `FilteringBoundLogger`.
- `app/db/base.py` — `Base(DeclarativeBase)`, `UUIDPrimaryKeyMixin`,
  `TimestampMixin`.
- `app/db/session.py` — lazily-constructed module-level `AsyncEngine` /
  `async_sessionmaker` (`pool_pre_ping=True`), `get_db()` FastAPI dependency,
  `dispose_engine()` for shutdown.
- `app/db/init.py` — `ensure_vector_extension(engine)`: `CREATE EXTENSION IF NOT
  EXISTS vector`. Called from `lifespan`, which is why `make migrate` (run after
  `make dev`) can create `VECTOR`-typed columns without its own extension setup.
- `app/db/types.py` — `EmbeddingVector = Vector(384)` (fixed to
  `sentence-transformers/all-MiniLM-L6-v2`'s output dimension — changing it means
  re-embedding the corpus and a new migration, not a config flip); `enum_values()`,
  a `values_callable` helper passed to every `str`-valued `sa.Enum(...)` column so
  Postgres stores the enum's lowercase `.value` instead of SQLAlchemy's default
  (the Python member's uppercase `.name`). `ServiceTier` in `catalog.py` is the one
  enum that does *not* use this helper — it's `int`-valued, and its DB labels are
  meant to be the member names (`TIER_1`/`TIER_2`/`TIER_3`).
- `app/models/*.py` — one file per domain, per plan.md §8 (see Data Model Changes).
- `app/main.py` — `create_app()` (FastAPI app factory: title/version, CORS from
  `Settings.cors_origins_list`, `RequestIDMiddleware`, the `AppError` handler,
  `/health`), `lifespan()` (configure logging → ensure vector extension → log
  `app_startup` with `llm_configured` → yield → dispose engine → log
  `app_shutdown`).
- `alembic/env.py` — async-mode Alembic environment; imports every `app.models.*`
  submodule so `Base.metadata` is fully populated before autogenerate runs.

## Dependencies

This module has no dependency on any other Hindsight backend module — it *is* the
base every later module (B3–B17) builds on: their route handlers will depend on
`app.core.deps`, their exceptions will subclass `app.core.errors.AppError`, their
models will import `app.db.base`/`app.db.types`, and their tables were already
created here.

External: FastAPI, Starlette, SQLAlchemy 2.0 (async) + `asyncpg`, Alembic,
`pgvector` (Python client + the Postgres extension), `pydantic`/`pydantic-settings`,
PyJWT, `argon2-cffi`, `structlog`.

## Sequence Flows

**App startup**
1. `create_app()` builds the FastAPI instance and registers middleware/handlers.
2. `lifespan()` runs on process start: `configure_logging()` →
   `ensure_vector_extension(engine)` → log `app_startup` (with `llm_configured`).
3. Requests are served. On shutdown: `dispose_engine()` → log `app_shutdown`.

**Authenticated, tenant-scoped request** (the shape every Phase 2+ route will use)
1. Client sends `Authorization: Bearer <access_token>`.
2. `get_current_user` decodes the JWT, loads the `User` by `sub`, 401s if the
   header is missing/malformed, the token is invalid/expired, or the user is
   missing/inactive.
3. `get_current_workspace` loads the `WorkspaceMember` row for
   `(workspace_id, current_user.id)`; 404s (never 403) if the caller isn't a
   member, so workspace existence isn't leaked to non-members.
4. If the route also depends on `require_role(*roles)`, the member's `role` is
   checked against the allowed set; 403 if it isn't in it.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Missing/malformed `Authorization` header | `UnauthorizedError` (401) |
| Expired or invalid JWT | `UnauthorizedError` (401), original `PyJWTError` chained via `from exc` |
| Access token decodes but user no longer exists / `is_active=False` | `UnauthorizedError` (401) |
| Caller queries a `workspace_id` they aren't a member of | `NotFoundError` (404), not 403 — avoids confirming the workspace exists |
| Caller is a member but lacks the required role | `ForbiddenError` (403) |
| DB unreachable when `GET /health` is called | Caught, never raised; response is `200` with `status: "degraded"`, `db_connected: false` |
| No LLM API key configured anywhere | App boots normally; `llm_configured: false`; nothing in this phase calls an LLM |
| Any `AppError` subclass raised in a handler | Rendered as `{"error": {code, message, detail}}` with the subclass's `status_code`, via the registered exception handler |
