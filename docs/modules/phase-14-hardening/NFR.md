# NFR: Hardening

## Performance

- Rate-limit checks (`TokenBucket.consume`) are O(1) dict lookups against in-memory
  state — no new database round trip on the hot auth/brief-generation paths.
- The request-size-cap middleware reads a header, not the body — no buffering cost for
  requests it rejects, and zero added cost for requests under the cap beyond one
  integer comparison.
- Security headers are static string writes on every response — immeasurable per-request
  cost, no new I/O.

## Security

- Rate limiting on `/auth/login`/`/auth/signup`/`/auth/refresh` is the actual point of
  this phase's auth-hardening: today these have zero backstop against credential
  stuffing or signup spam, unlike `/auth/demo` which Phase 11 already bounded.
- The global exception handler's entire purpose is preventing information disclosure —
  an unhandled exception's message, type, and traceback must never reach the client,
  only the structured server-side log. Verified by a test that raises a deliberate bug
  and asserts the response body contains neither the original exception's class name
  nor its message string.
- `X-Frame-Options: DENY` and CORS's origin allowlist (unchanged, already strict since
  Phase 2) together are this API's clickjacking/cross-origin-embedding defense — the
  API itself renders no HTML, so this matters for how a browser treats *responses from*
  this origin when something else tries to frame/fetch them, not for content this app
  serves.
- `Strict-Transport-Security` is gated on `cookie_secure` (prod-only) deliberately —
  sending HSTS over plain local HTTP would make `http://localhost` unusable in some
  browsers for the rest of its cache lifetime, a self-inflicted dev-environment outage
  Phase 2's `cookie_secure` flag already exists to prevent for cookies and now also
  prevents here.
- The request-size cap and the LLM-call timeout are both resource-exhaustion defenses:
  one bounds how much a single request can make the app buffer/parse, the other bounds
  how long a single request can hold a worker/connection waiting on a slow external
  provider.

## Reliability

- `TokenBucket` remains in-memory, single-process, unshared across replicas — an
  accepted limitation at this project's scale, same call as Phase 2's NFR and Phase
  11's `demo_signup_bucket`/`demo_brief_bucket`. A horizontally-scaled deployment would
  under-enforce these limits (each replica has its own bucket); not a concern for a
  single-instance portfolio deployment, and documented here so it's a known tradeoff,
  not a silent gap.
- The global exception handler makes the app more reliable in the specific sense that
  *a bug in one request can no longer produce an unstructured, unlogged failure* — every
  failure mode now produces a structured log line with a correlation id, which is the
  actual prerequisite for ever debugging a production incident in this app.
- LLM call timeouts prevent a single slow/hung provider from indefinitely occupying a
  request — combined with `LLMRouter`'s existing fallback-on-failure behavior (Phase
  6), a timeout on one provider now correctly triggers the next provider in the chain
  rather than hanging.

## Observability

- New structlog event: `unhandled_exception` (request_id, exception type, full
  traceback via `logger.exception`) — the one new event this phase adds; every other
  hardening change (rate limits, headers, size cap) reuses `RateLimitedError`'s
  existing error-response path, which already logs nothing extra beyond what
  `app_error_handler` always has (the response body itself is the record).
- `request_id` now appears in every error response body, not just the `X-Request-ID`
  header — closes the gap where a client-side error toast/log had no way to hand a
  support/debug request a correlation id without also capturing raw response headers.

## Testability

All of the below live in one `test_hardening.py`, grouped into classes by concern
(`TestRateLimiting`, `TestErrorHandling`, `TestSecurityHeaders`, `TestRequestSizeCap`,
`TestTokenBucket`, `TestNPlusOneRegressionGuard`) rather than one file per FR — each
class is small enough that a separate file per concern would just be import overhead
for no organizational benefit:

- Rate limiting: login 429 past threshold with a `request_id` in the body; `/refresh`
  confirmed *not* rate-limited even under heavy repeated calls; brief generation 429
  past its own independent per-workspace threshold; a different workspace's bucket
  confirmed independent.
- Error handling: a route that deliberately raises a plain `Exception` returns the
  generic envelope with a `request_id` and no leaked internals (asserted by string
  absence, not just status code); a typed `AppError`'s envelope also carries
  `request_id`.
- Security headers: every response carries the three unconditional headers; HSTS
  confirmed *absent* under this test build's `cookie_secure=False`, the honest
  negative counterpart proving the gate is real.
- Request size cap: an oversized body 413s before any service function runs; a
  normal-sized request is unaffected.
- `TestNPlusOneRegressionGuard` (FR-08): the query-count regression guard for
  `list_postmortems`, seeding 2 vs. 50 rows and asserting the SQL statement count
  stays identical.

`test_tenant_isolation.py` (FR-09) is its own file, separate from `test_hardening.py`,
since it's structurally different — a generator over the app's own route table, not a
set of hand-written cases — with its own two meta-tests (the generator finds a sane
minimum number of routes; every matching route is either covered by a fixture or has a
documented `KNOWN_UNCOVERED` reason) plus one parametrized test per covered route.

## Constraints

- No new database table/column — everything in this phase is either in-memory state
  (rate limits) or stateless middleware/handler behavior.
- Async throughout; full type hints; mypy strict clean, matching every prior phase.
- No hardcoded timeout/size-cap value inline — both are `Settings` fields with
  documented defaults (`llm_request_timeout_seconds=30`, `max_request_bytes=15_728_640`),
  overridable via environment, matching this project's existing convention for every
  other tunable (`critic_threshold`, `job_lease_seconds`, etc.).
