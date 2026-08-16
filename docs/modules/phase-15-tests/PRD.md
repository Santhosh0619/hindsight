# PRD: Tests

Phase: 15
Module codes: cross-cutting — no new B<X>/F<X> row in plan.md §6, same shape as Phase
14. Backend-only; no new frontend work.

## Problem

Master-Prompt.md's Phase 15 checklist reads like a from-scratch test-writing phase,
but this codebase has been writing real tests since Phase 1 — auditing the existing
39 backend test files against that checklist shows most of it already exists:
`test_auth.py` (signup/login/refresh/rotation/reuse-detection/logout), `test_graph.py`
(chain/diamond/cycle/depth-cap/criticality), `test_ingestion.py` (redaction/chunking/
injection screening), `test_retrieval.py` (RRF math, per-mode result sets),
`test_queue.py` (concurrent claim/backoff/dead-letter/lease-reclaim), and
`test_agent_pipeline.py`/`test_route_after_critic.py` together covering the routing
truth table, one-retry-then-exit, invalid-citation rejection, and no-LLM degradation
the checklist's `test_agents.py` describes. Phase 14 already built
`test_tenant_isolation.py`, which is exactly the checklist's `test_tenancy.py` entry
("the generated cross-tenant test from Phase 14"). This phase's real job is threefold:
find and close the genuine gaps (a dedicated RBAC role-matrix sweep and a full
endpoint-status-code smoke test — neither exists as a standalone file today), fix one
real "no test touches the network" violation the audit found, and make test coverage
on `services/`/`agents/` visible rather than just assumed.

## Actors

- **A future contributor** (including a future version of the assistant building later
  phases) — the two new generated tests (`test_rbac.py`, `test_api_smoke.py`) exist
  specifically so a new mutating endpoint that forgets its role gate, or a new route
  that returns an undocumented status code, is caught mechanically instead of relying
  on someone remembering to hand-write a case.
- **Anyone reviewing this project's rigor** — a visible coverage report on the modules
  that matter (`services/`, `agents/`) is a concrete answer to "how do you know this is
  actually tested," not just an assertion.

## Functional Requirements

FR-01: A generated RBAC role-matrix test (`test_rbac.py`) iterates the app's own route
table (reusing the traversal technique `test_tenant_isolation.py` already built in
Phase 14) to find every mutating endpoint (`POST`/`PATCH`/`DELETE` under
`/workspaces/{workspace_id}/...`), and for each one mechanically asserts a `viewer`
session gets 403, not 200/201/204 — mirroring FR-09's `KNOWN_UNCOVERED`-with-a-reason
pattern for any route it can't construct a fixture for.

FR-02: A generated endpoint smoke test (`test_api_smoke.py`) iterates the same route
table and asserts every endpoint returns one of its documented status codes for a
minimal valid/invalid request — not deep behavioral coverage (that's what the rest of
the suite is for), just "this route is wired up and doesn't 500 on a request shaped
roughly like what it expects."

FR-03: `test_settings_api.py::test_llm_test_reports_unconfigured_slots_without_calling_them`
no longer makes a real (if harmless, local, fast-failing) network connection attempt
to `ollama_base_url` — the one confirmed violation of "no test touches the network"
found during the audit. The Ollama slot's real-reachability behavior is instead
verified against a mocked/monkeypatched provider.

FR-04: `pytest-cov` is wired into the backend test run (`make test-be` and CI), and
reports coverage for `app/services/` and `app/agents/` specifically — visible in every
local/CI run, not gating a hard percentage threshold (per Master-Prompt.md's own "do
not chase a coverage number" instruction), and explicitly excluding generated/
boilerplate model files (`app/models/`, `app/schemas/`) from the reported figure so
the number reflects the code that actually has logic to test.

## User Stories

As a future contributor, I want a new mutating endpoint's missing role check to fail a
test automatically, so that an RBAC gap is caught before it ships, not discovered by a
viewer who shouldn't have been able to do something.

As anyone auditing this project, I want to see a real coverage percentage for the
service and agent layers, so "this is well-tested" is a number I can check, not a
claim I have to take on faith.

As a developer running the suite locally or in CI, I want every test to be fully
offline-deterministic, so a flaky network path never causes a false failure on an
otherwise-correct change.

## Out of Scope

- Chasing 100% coverage, or gating CI on a coverage threshold — Master-Prompt.md
  explicitly says not to, and a hard gate would pressure padding tests around
  generated Pydantic/SQLAlchemy model files instead of testing real logic.
- Rewriting or restructuring the 39 existing test files to match the checklist's exact
  filenames (e.g. renaming `test_agent_pipeline.py` to `test_agents.py`) — the
  coverage the checklist asks for already exists under names that reflect this
  project's own established per-module test-file convention; renaming working,
  reviewed test files for cosmetic alignment with a planning doc's suggested names
  isn't worth the churn.
- A frontend/e2e test audit — this phase is backend-only per Master-Prompt.md's own
  Phase 15 section (no F<X> work listed).

## Acceptance Criteria

- `make test` (backend) is green; `make lint`/`make typecheck` clean — the literal
  Master-Prompt.md checkpoint.
- `test_rbac.py` fails (red) if a mutating endpoint's role dependency is deliberately
  removed during development, and passes (green) against the current, correct
  codebase — the same falsifiability bar Phase 14's tenant-isolation generator set.
- Running the full backend suite makes zero real network connections — verified by
  running it with network access disabled/blocked and confirming no test errors out on
  a connection attempt.
- A coverage report for `app/services/` and `app/agents/` is produced on every
  `make test-be`/CI run, visible in the output.
