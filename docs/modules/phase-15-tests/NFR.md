# NFR: Tests

## Performance

- `test_rbac.py`'s 23 cases and `test_api_smoke.py`'s ~58-route sweep are each one
  HTTP round trip per case over the in-process ASGI transport — no new database
  fixtures beyond a signup + one role-demotion UPDATE per case, comparable cost to any
  other single-assertion test already in the suite. Not expected to noticeably move
  the full suite's runtime (229 tests, ~17 minutes as of Phase 14's last clean run;
  these ~80 new cases are each sub-second).
- Coverage instrumentation (`pytest-cov`) adds real per-run overhead (line-tracing has
  a measurable cost), scoped to `app/services`/`app/agents` only rather than the whole
  `app/` package specifically to keep that overhead bounded to the code the number is
  actually about.

## Security

- `test_rbac.py` is itself a security-relevant test: it's the mechanical backstop
  against a class of bug (a new mutating endpoint that forgets its role dependency)
  this project has cared about enforcing since Phase 2's `workspace_id`-everywhere
  discipline. Its own correctness (verified pre-implementation, not assumed) is
  documented in the FRD and ADR specifically because a role-matrix test that's
  subtly wrong (e.g. checking the wrong status code, or accidentally testing as
  `owner` instead of `viewer`) would be worse than no test — it would look like
  RBAC coverage without providing any.
- Removing the real network touch in `test_settings_api.py` (FR-03) has a security
  angle too, not just a hygiene one: a CI runner or a contributor's machine making an
  unexpected outbound connection during a test run — even a local, fast-failing one —
  is exactly the kind of thing a hardened CI pipeline (this project's own Phase 14
  concern, one phase earlier) should have zero of, on principle.

## Reliability

- "No test touches the network" is a reliability property as much as a security one:
  a test whose pass/fail depends on a real socket connection's behavior (even to
  `localhost`) is non-deterministic across environments in a way a fully mocked test
  isn't — a CI runner's network namespace, a contributor's local firewall, or a
  future Ollama actually running on `localhost:11434` for local development could all
  silently change this test's outcome. Mocking it makes the test's result depend only
  on the code under test.
- `test_api_smoke.py` deliberately asserts *never 500*, not deep behavioral
  correctness — its reliability value is specifically as an early-warning trip wire
  for "this route is broken in a way that would surprise every caller," a narrower and
  cheaper guarantee than what the rest of the suite already provides.

## Testability

- This entire phase is testing infrastructure, so its own "testability" section is
  about how the two new generated tests themselves get verified, not just what they
  verify: both were validated before being written by directly querying the running
  app's real dependency-resolution order (see ADR) rather than assumed from reading
  FastAPI's general documentation, the same empirical-first discipline Phase 14's
  tenant-isolation generator and this phase's own design both depend on.
- Coverage output (FR-04) itself becomes part of what a future phase's TEST-BE step
  can look at — not a gate, but a number that should trend flat-or-up over time as new
  service/agent code lands; a real drop would be worth investigating even without a
  hard threshold forcing the question.

## Constraints

- No new database table/column, no new API route, no new frontend code — this phase
  changes zero runtime behavior; every change is either a new test file or a
  monkeypatch inside an existing test.
- `pytest-cov`'s coverage flags are additive to the existing `pytest` invocation in
  `Makefile`/CI, not a new command or a new CI job — matches this project's existing
  preference for extending an established gate over adding a parallel one.
- Async throughout for every new async test function; full type hints; mypy strict
  clean, matching every prior phase (test files are covered by `mypy app --strict`'s
  own existing scope only insofar as they already were — this phase doesn't change
  that boundary).
