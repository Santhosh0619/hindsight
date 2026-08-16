# FRD: Hardening

## API Endpoints (Backend — FastAPI)

No new endpoints. Existing endpoints gain new failure modes and response headers.

### `POST /auth/login`, `POST /auth/signup`
- New error code: 429 `rate_limited` past a per-IP `TokenBucket` threshold, identical
  envelope shape to `/auth/demo`'s existing 429. `/auth/refresh` is unchanged — see
  PRD "Functional Requirements" FR-01 for why it's excluded.
- Every response (success or error) now carries `X-Request-ID`, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, and (prod only) `Strict-Transport-Security`.

### `POST /workspaces/{id}/incidents/{id}/brief`, `GET .../brief/stream`
- New error code: 429 `rate_limited` past a per-workspace `TokenBucket` threshold,
  independent of the Phase 11 demo-guest bucket already gating these routes for demo
  sessions.

### Every endpoint (global)
- 413 `request_too_large` if `Content-Length` exceeds `settings.max_request_bytes`,
  raised before the body is parsed.
- Any previously-unhandled exception now returns 500 with the standard `AppError`
  envelope shape (`code: "internal_error"`), never the exception's own message, and
  always includes `request_id` in the JSON body.

## React Components (Frontend)

None. This phase has no F<X> screen — see PRD "Out of Scope"/Master-Prompt.md's own
phrasing (a pure backend/infra pass).

## Data Model Changes

None. Rate-limit state is in-memory (`TokenBucket`, unchanged shape from Phase 11); no
new table, no new column.

## Internal Architecture

### Rate limiting (`app/services/rate_limit.py`, `app/api/v1/auth.py`, `app/api/v1/incidents.py`)

- Two new module-level `TokenBucket` instances alongside the existing
  `demo_signup_bucket`/`demo_brief_bucket`: `login_bucket` (keyed by client IP,
  capacity 30/60s — generous enough that no real user or the e2e suite's own rapid
  signup/login traffic ever trips it, while still bounding automated credential
  stuffing to a rate password hashing's own cost already makes expensive per attempt)
  and `brief_bucket` (keyed by `workspace_id`, since brief generation cost is a
  workspace-level concern, not an individual caller's). `signup` reuses `login_bucket`
  — same threat model as login, automated abuse of a cheap-to-call auth endpoint, and
  Phase 11's own precedent is one bucket per *concern*, not one per route.
  `/auth/refresh` deliberately does not consume this bucket at all (see PRD FR-01) —
  discovered during implementation that it fires on every page load's boot-time
  session restore (57+ times across the e2e suite alone), so gating it would throttle
  ordinary navigation for no real security benefit, since it isn't a
  guessable-credential endpoint in the first place.
- `auth.py`'s existing `_client_ip(request)` helper (already handles the
  `X-Forwarded-For` proxy case, per its own docstring) is reused for the new checks,
  not reimplemented.
- `incidents.py`'s `generate_brief`/`stream_brief` routes check `brief_bucket.consume
  (str(workspace_id))` before doing any real work — before the demo-guest carve-out's
  own bucket check where both apply, so a demo guest is still bounded by both limits
  independently, matching FR-02's "independent of the demo bucket" requirement.

### Global exception handling (`app/core/errors.py`, `app/main.py`)

- New `app_unhandled_exception_handler(request, exc)` registered via
  `app.add_exception_handler(Exception, ...)` — Starlette dispatches the most specific
  registered handler first, so this only ever fires for exceptions `AppError`'s own
  handler doesn't already catch. Logs `structlog`'s full exception info
  (`logger.exception("unhandled_exception", ...)`, which captures the traceback) with
  the request's `request_id` (already bound to structlog's contextvars by
  `RequestIDMiddleware`), then returns a `JSONResponse` with the same envelope shape as
  `AppError`'s handler: `{"error": {"code": "internal_error", "message": "An
  unexpected error occurred", "detail": null}}` plus `request_id` at the top level of
  `error`.
- `app_error_handler` (the existing `AppError` handler) gains the same `request_id`
  field in its envelope, read from `structlog.contextvars.get_contextvars()` — both
  handlers share one small helper (`_current_request_id() -> str | None`) so the two
  envelopes can't drift apart in shape.

### Security headers (`app/core/security_headers.py`, new; wired in `app/main.py`)

- A small `BaseHTTPMiddleware` subclass, `SecurityHeadersMiddleware`, added after
  `RequestIDMiddleware` in the stack (order doesn't matter between these two — neither
  reads the other's output — but keeping request-id first matches the existing
  convention of identity/tracing middleware running outermost). Sets
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin` unconditionally; sets
  `Strict-Transport-Security: max-age=63072000; includeSubDomains` only when
  `settings.cookie_secure` is `True` — the same flag that already distinguishes "real
  deployment" from "local plain-HTTP dev" (Phase 2's own precedent), so this doesn't
  need a new setting.

### CORS tightening (`app/main.py`)

- `allow_methods` narrowed from `["*"]` to `["GET", "POST", "PATCH", "DELETE"]` (the
  full set any route in this API actually declares — verified by grepping every
  `@router.<verb>` decorator across `app/api/v1/`). `allow_headers` narrowed to
  `["Content-Type", "Authorization", "X-API-Key"]` (session bearer token, the ingest
  webhook's key header, and the content-type every JSON request sends).
  `allow_origins`/`allow_credentials` unchanged.

### Request size cap (`app/core/request_size.py`, new; wired in `app/main.py`)

- A `BaseHTTPMiddleware` subclass reading `Content-Length` off the incoming request
  before calling `call_next`; if present and over `settings.max_request_bytes`
  (new setting, default `15_728_640` — 15MB, deliberately *above*
  `max_upload_bytes`'s own 10MB text cap, not below it — a legitimate postmortem's
  `raw_text` can sit right up against that 10MB field limit plus JSON structure
  overhead, so this outer check must never be tighter than the field-level cap it
  wraps, or it would reject requests the field validator was always meant to allow.
  The two caps intentionally differ in *kind*, not just size: `max_upload_bytes`
  bounds one specific field's *character* count post-parse, `max_request_bytes`
  bounds the *whole request body's byte size* pre-parse as a cheap first line of
  defense against a request nowhere near legitimate (hundreds of MB) — a request
  missing `Content-Length` (chunked transfer) is let through to normal
  parsing/validation rather than blocked, since this is a
  defense-in-depth measure, not the only size check in the system.

### Outbound LLM call timeouts (`app/services/llm/{gemini,groq,ollama}.py`)

- Each provider's `pydantic_ai.Agent` construction now passes an explicit
  `model_settings={"timeout": settings.llm_request_timeout_seconds}` (new setting,
  default `30`) — previously relied on pydantic-ai/httpx's own default, which exists
  but was never an explicit, documented, project-owned value per Master-Prompt.md's
  "document why" instruction. `llm_test_service.py`'s connection-test calls inherit the
  same explicit timeout via the same provider construction path, not a second value.

### N+1 audit (documentation, no functional code change expected)

- Every list-returning service function was read directly (not sampled): 
  `postmortem_service.list_postmortems` (batches affected-services via one IN-clause
  query, `_affected_services_by_postmortem_id`), `incidents_service.list_incidents`/
  `list_briefs`, `agent_run_service.list_runs`/`get_run_detail` (single JOIN query for
  run+incident-title+cache-flag, no per-row query), `catalog_service.list_services`/
  `get_graph`, `incidents_service._enrich_blast_radius` (batches via
  `catalog_service.get_services_by_ids`, one IN-clause query for every referenced
  service across every blast-radius entry, not one query per entry),
  `workspace_service.list_members`/`list_audit_log`, `dashboard_service`'s aggregate
  queries. **Finding: no N+1 pattern exists in any of them** — every one already
  either issues a single query with a `JOIN`/`IN` clause or iterates an
  already-fully-fetched `result.all()`/`result.scalars().all()` in Python. This is a
  verified, not assumed, negative result — see ADR for the honest-finding writeup
  precedent (same posture as Phase 12 §3's tied ablation).
- A regression-guard test (`test_hardening.py::test_list_postmortems_query_count_stays_flat_as_rows_grow`)
  uses SQLAlchemy's `event.listen(engine.sync_engine, "before_cursor_execute", ...)` to
  count statements issued while calling `list_postmortems` against a 1-row vs. a
  50-row fixture, asserting the count is identical — proving the batching is real, not
  just plausible from reading the code, and catching a future regression that
  reintroduces a per-row query.

### Generated tenant-isolation test (`tests/test_tenant_isolation.py`, new)

- Iterates `app.routes` (the real `FastAPI` app's own route table, imported from
  `app.main`) at test collection/run time, filtering to routes whose path template
  contains a second path parameter nested after `{workspace_id}` (e.g.
  `/workspaces/{workspace_id}/postmortems/{postmortem_id}`,
  `/workspaces/{workspace_id}/agent-runs/{run_id}`) and whose method is `GET` — a GET
  is the only method every such route universally supports and the only one safe to
  call generically without knowing each route's own write-payload shape. For each
  matching route: creates workspace A with one real resource of the relevant kind
  (reusing each module's own existing test fixtures/helpers where one already creates
  that resource type, e.g. `_create_incident` from `test_agent_runs_api.py`) and
  workspace B with none, substitutes A's real resource id into the path template, and
  asserts a session authenticated as workspace B's owner gets 404 — never the
  resource. Routes this can't mechanically construct a fixture for (none currently
  match the filter without an existing helper) are listed explicitly in a
  `KNOWN_UNCOVERED` set with a one-line reason, so the generator's own coverage is
  visible rather than silently partial.

## Dependencies

- Calls: `app.services.rate_limit.TokenBucket` (Phase 11, extended not replaced),
  `app.core.logging` (`RequestIDMiddleware`'s contextvars, unchanged), every existing
  service module (read-only, for the N+1 audit).
- Called by: every route in the app (global middleware/exception-handler changes);
  `app.services.llm.router.LLMRouter` (timeout now explicit at the provider level it
  already delegates to).

## Sequence Flows

### A brute-forced login attempt
1. Client `POST /auth/login` with a guessed password, repeated rapidly from one IP.
2. `_client_ip(request)` resolves the caller's IP (proxy-aware).
3. `login_bucket.consume(client_ip)` returns `False` once the bucket empties.
4. Route raises `RateLimitedError` → `app_error_handler` → 429 envelope with
   `request_id`, `X-Request-ID` header set by `RequestIDMiddleware`, security headers
   set by `SecurityHeadersMiddleware` — same as any other response.

### An unexpected bug in a request handler
1. A route/service raises a plain `Exception` (a real bug, not a typed `AppError`).
2. FastAPI/Starlette finds no handler registered for the specific exception type,
   falls back to the `Exception`-registered handler.
3. `app_unhandled_exception_handler` logs the full traceback + `request_id` via
   `logger.exception(...)`, returns the generic `internal_error` envelope.
4. `RequestIDMiddleware` still attaches `X-Request-ID` to this response — it received
   a normal `Response` object back from `call_next`, not a propagated exception, since
   the exception was already handled by the registered handler before this middleware
   saw it.

## Edge Cases & Error Handling

- **A request with no `Content-Length` header at all** (e.g. chunked transfer
  encoding): the size-cap middleware doesn't block it — it's not a bypass so much as
  an accepted gap in a defense-in-depth check; the app's normal request-body parsing
  and Pydantic field-level validation (`max_upload_bytes`, per-field `max_length`
  constraints) remain the actual enforcement boundary for such a request.
- **A rate-limited demo-guest brief-generation call**: bounded independently by both
  `demo_brief_bucket` (Phase 11, scoped to demo guest sessions specifically) and the
  new workspace-level `brief_bucket` — whichever empties first returns 429; this is
  intentional layering, not a bug, since the two buckets protect against different
  things (one caller minting excessive demo sessions vs. one workspace's aggregate
  brief-generation rate).
- **An `AppError` subclass raised from inside a background-adjacent SSE stream**
  (`/brief/stream`): the global exception handler and security-headers middleware
  apply identically to streaming responses — no separate code path, since both are
  ASGI-level middleware/handlers that don't distinguish response type.
- **The tenant-isolation generator finding zero matching routes** (e.g. if every
  nested-resource route were somehow removed): the test would then trivially pass with
  zero assertions, which is silently useless — guarded against with an assertion that
  the generator finds at least N known routes (a hardcoded minimum, not a coincidence
  of what happens to exist today), so a collection bug in the generator itself fails
  loudly instead of looking like "everything passed."
