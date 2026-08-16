# FRD: Tests

## API Endpoints (Backend — FastAPI)

None new. This phase adds tests against existing endpoints; no route changes.

## React Components (Frontend)

None. Backend-only phase, matching PRD "Out of Scope".

## Data Model Changes

None.

## Internal Architecture

### `backend/tests/test_rbac.py` (new) — generated role-matrix sweep

- Reuses `test_tenant_isolation.py`'s route-table traversal (`app.routes` →
  `route.original_router.routes`, filtered to methods `{"POST", "PATCH", "DELETE"}`
  and paths containing `{workspace_id}`) to enumerate every mutating endpoint — 23
  routes as of this phase, spanning workspaces/members/catalog/postmortems/incidents/
  apikeys/settings.
- Confirmed empirically before writing any test code (see ADR): this FastAPI
  version's dependency resolution runs the route's `Depends(require_role(...))` check
  *before* both Pydantic body validation and any resource-id lookup — a `viewer`
  session gets 403 for a mutating route even with an empty/missing JSON body and a
  syntactically-valid-but-nonexistent path-param UUID. This means the generated test
  needs no per-route fixture-creator registry (unlike `test_tenant_isolation.py`,
  which genuinely needs a real resource to test against workspace *B*'s inability to
  read it) — every case is: sign up an owner, demote to `viewer`, substitute
  `{workspace_id}` with the real one and every other path param with a fresh random
  UUID, send an empty JSON body (or none, for routes that take none), assert 403.
- A small, explicit `EXPECTED_MIN_ROUTES` meta-test guards the generator itself the
  same way `test_tenant_isolation.py`'s does — a route-discovery regression that
  silently found zero routes would make every case vacuously pass.
- Because the role check wins over body validation regardless of a route's request
  body shape (verified above, including for `POST .../catalog/import`'s nested
  teams/services/edges payload), every mutating route the traversal finds is actually
  coverable by the single generic case — there's no `KNOWN_UNCOVERED` entry in the
  current route set. The `KNOWN_UNCOVERED` dict stays in the file empty but present
  (mirroring `test_tenant_isolation.py`'s structure exactly), so a future route that
  genuinely can't be tested this way has a documented place to go rather than
  silently vanishing from the sweep or blocking the meta-test with no explanation.

### `backend/tests/test_api_smoke.py` (new) — every endpoint answers, on-contract

- A lighter-weight second pass over the *entire* route table (not just mutating
  routes) — for each endpoint, sends a minimal request (empty body where one is
  accepted, a valid auth header, real path-param values where the route needs a real
  resource to do anything meaningful) and asserts the response status is one of that
  route's own documented codes from its FRD, never a bare 500. This is a shallow
  "is this endpoint wired up and does it fail cleanly on a boundary case" check, not a
  substitute for each module's own deep behavioral tests — genuinely valid-body
  happy-path testing already exists per-module across the other 39 test files.
- Read-only (`GET`) routes are exercised directly. Mutating routes are exercised as an
  authenticated `owner` (not `viewer`, since `test_rbac.py` already owns that axis)
  with an empty body, asserting the response is `422` (this codebase's own
  `ValidationAppError` shape) rather than `500` — proving the route's Pydantic model
  and error handling are wired correctly, without needing a full valid payload.

### `backend/tests/conftest.py` — no production code change

- The audit's real network violation turned out bigger than the one test that
  surfaced it: `OllamaLLMProvider` is *always* constructed regardless of whether an
  LLM key is configured (Ollama needs none), by two separate call paths —
  `llm_test_service.test_all_providers` (the `/settings/llm/test` route) *and*
  `build_router()`, which is called for real inside the actual `POST
  .../incidents/{id}/brief` route handler, not just in an LLM-specific unit test. Any
  test exercising either path — including, as this phase found, the new generated
  `test_api_smoke.py` sweep, which touches both — was making a real (local,
  fast-failing, but real) TCP connection attempt to `ollama_base_url`. Fixed once, at
  the source, with a new `autouse` fixture in `conftest.py` that monkeypatches
  `OllamaLLMProvider`'s three `LLMProvider` protocol methods (`complete`/`structured`/
  `structured_with_usage`) at the *class* level — not per-module import site — so
  every current and future call path through it is covered by construction, rather
  than requiring every test file that happens to exercise one of those routes to
  remember its own mock. `test_settings_api.py`'s own test needed no file-local mock
  at all once this landed; its assertions (`configured=True`, `ok=False`, `error`
  populated, `latency_ms` present) are unchanged, now reached with zero real sockets
  opened.

### `backend/pyproject.toml`, `Makefile` — coverage visibility

- `pytest-cov` added to `[project.optional-dependencies].dev`. `make test-be` and the
  CI `Backend` job both gain `--cov=app/services --cov=app/agents
  --cov-report=term-missing` on the existing `pytest` invocation — no new command, no
  new CI step, coverage is just additional output on the run that already exists.
  Explicitly scoped to `services/`/`agents/` (per PRD FR-04) rather than the whole
  `app/` package, so `app/models/`/`app/schemas/`/`app/api/v1/` (thin routers, already
  exercised indirectly by every other test) don't dilute or inflate the number either
  direction.

## Dependencies

- Calls: `app.main.app`'s own route table (read-only introspection, same pattern as
  Phase 14); every existing service/agent module (coverage measurement only, no
  behavior change).
- Called by: nothing new — this phase adds tests, not code other modules depend on.

## Sequence Flows

### The RBAC sweep, one case

1. Sign up a fresh user (becomes `owner` of a fresh personal workspace, existing
   `signup()` helper).
2. Demote that membership to `viewer` directly via the `db` fixture (matching the
   existing per-module pattern already used in `test_catalog.py`,
   `test_settings_api.py`, etc. — not a new technique).
3. For the route under test, build the real path (`workspace_id` substituted with the
   real one, every other `{param}` substituted with `uuid.uuid4()`), send the route's
   method with an empty JSON body.
4. Assert `403`, and assert the envelope's `error.code == "forbidden"` — not just the
   status code, matching the same discipline `test_tenant_isolation.py`'s fix added
   this project's generated tests (a bare status-code check that happens to match a
   different failure mode isn't proof the real check ran).

## Edge Cases & Error Handling

- **A route requiring no body at all** (most `DELETE`s, some `POST`s like
  `invite-code`): the generator sends no `json=` kwarg rather than an empty dict —
  confirmed both produce identical 403 behavior during the pre-implementation
  verification, but omitting the body for a body-less route matches what a real
  caller would actually send.
- **A route whose path has more than one non-`workspace_id` parameter** (none exist
  in the current mutating-route set, but the generator doesn't assume exactly one —
  it substitutes every `{param}` found, the same general approach as
  `test_tenant_isolation.py`'s `_id_kwargs`, generalized to N params instead of
  exactly one).
- **Coverage measurement and the real Postgres-backed test suite**: `pytest-cov`
  measures Python line/branch execution, not SQL coverage — a service function that's
  "covered" by a test still only proves the Python code path ran, not that every
  branch of generated SQL was meaningfully exercised. This is a known, accepted
  limitation of line coverage as a metric in general, not something this phase's
  tooling choice can fix; the NFR's "don't chase a number" framing already accounts
  for coverage being a floor, not a ceiling, on actual test quality.
