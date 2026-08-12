# ADR 0001: Phase 1 Foundation — Schema, Tooling, and E2E Deferral

## 1. Enum columns store lowercase values, not Python member names

**Context.** SQLAlchemy's `Enum(SomeEnumClass, name=...)` column type persists the
Python enum member's `.name` (e.g. `QUEUED`) as the Postgres enum label by default. Every
enum in `app/models/` is defined with lowercase `.value`s (e.g. `queued`), and code that
predates the enum handling — like `jobs`'s partial-index predicate
`WHERE status = 'queued'` — already assumed those lowercase labels exist in the database.
Autogenerating the migration with the default behaviour created Postgres enums with
uppercase labels, which crashed the first real query against them with `invalid input
value for enum job_status: "queued"`.

**Decision.** Added a shared `enum_values()` helper in `app/db/types.py`, passed as
`values_callable` to every `str`-valued `Enum(...)` column across all eleven affected
enums (`workspace.py`, `catalog.py`, `postmortem.py`, `incident.py`, `job.py`), so the
Postgres label matches the Python `.value` the rest of the app already uses.
`ServiceTier` in `catalog.py` is the one exception — it's `int`-valued
(`TIER_1`/`TIER_2`/`TIER_3`), so its DB labels are meant to be the member names, and it
correctly skips the helper. Alternative considered and rejected: rename every enum's
Python member to lowercase to match SQLAlchemy's default — rejected because Python
convention is uppercase enum members, and fixing the column mapping once is a smaller,
more honest change than fighting that convention everywhere.

## 2. `mypy` type-checks against Python 3.12 while the app runs on 3.11

**Context.** `numpy` 2.5.2's bundled `.pyi` stubs (pulled in transitively via
`pgvector`/`sentence-transformers`) use the PEP 695 `type` statement unconditionally.
mypy refuses to *parse* that syntax under `python_version = 3.11` — this is a parser
limitation, not a semantic type error, so no per-module `ignore_errors` or
`follow_imports` override could suppress it while still targeting 3.11.

**Decision.** `backend/mypy.ini`'s `python_version` is bumped to `3.12` for
type-checking purposes only; the actual runtime target is unchanged (`pyproject.toml`'s
`requires-python = ">=3.11"`, `backend/Dockerfile`'s `python:3.11-slim` base image). To
keep the parse fix from also silently loosening checks on numpy's actual (unrelated)
type surface, `[mypy-numpy]` and `[mypy-numpy.*]` are additionally set to
`follow_imports = skip`, so numpy's stubs are never parsed at all rather than parsed
under a version they weren't written for. Alternative rejected: vendoring a fixed numpy
stub — more maintenance than a two-line config bump for a third-party stub bug.

## 3. `.gitignore`'s bare `models/` pattern was excluding the ORM source tree

**Context.** `.gitignore` had a bare `models/` entry meant to exclude a downloaded
ML-model-weights cache. Git's ignore patterns aren't path-anchored by default, so it
matched *any* directory named `models/`, including `backend/app/models/` — the
SQLAlchemy ORM source for the entire schema. Every file in it was silently untrackable;
none of it could have entered a commit.

**Decision.** Removed the bare pattern; kept the extension-based ignores (`*.bin`,
`*.safetensors`, `*.onnx`) since the actual model-weight cache lives in the
`model-cache` Docker volume (`docker-compose.yml`), not a repo path, so the directory
pattern was never actually protecting anything. Verified via `git check-ignore` that
`backend/app/models/` is now tracked normally before committing Phase 1's code.

## 4. Phase 1 has no Playwright e2e run; health-check tests stand in for it

**Context.** The e2e-tester skill's isolated stack (`docker-compose.test.yml`) starts
`web-test` (needs `frontend/package.json`, which doesn't exist until Phase 3) and runs
`api-test`'s command through `python -m app.seed.seed` (which doesn't exist until Phase
11). Standing up that stack for Phase 1 would fail on dependencies that are deliberately
out of scope for this phase per its own PRD.

**Decision.** Per Master-Prompt.md's error-recovery rule ("a library's API differs from
this document: the library wins, adapt and record the deviation"), Phase 1's
verification gate is the `GET /health` behaviour itself, covered by `pytest` integration
tests (`backend/tests/test_health.py`) that exercise the real ASGI app end-to-end
through both its DB-reachable and DB-unreachable branches, plus unit coverage of the
security/pagination primitives. Full Playwright e2e coverage resumes at Phase 3 (once
there's a user-facing journey to click through) and the isolated compose stack becomes
runnable again once Phase 11 lands `app.seed.seed`.
