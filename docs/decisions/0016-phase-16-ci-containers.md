# ADR 0016: CI & Containers — Auditing a Checklist That Was Already Done

## 1. Most of Phase 16's checklist was built in Phase 1, out of necessity

**Context.** Master-Prompt.md's Phase 16 section reads as if CI and container tooling
starts here, at phase 16 of 18. It doesn't: `.github/workflows/ci.yml` (Postgres+
pgvector, `ruff`, `mypy`, `pytest`, frontend `tsc`/`build`, migration up→down→up) and
both multi-stage Dockerfiles (backend non-root with a `/health` healthcheck, frontend
build-to-`nginx` with its own healthcheck) have existed since Phase 1 (ADR 0001) —
waiting until phase 16 of 18 to add any automated check would have meant 15 phases of
real work landing with nothing catching a regression. This is the third phase in a row
(after 14 and 15) where the real work was auditing an existing checklist item by item
against what the codebase actually does, not building from a blank slate.

**Decision.** Confirmed and recorded the audit (FRD's checklist table) rather than
re-touching working CI/Dockerfile config for cosmetic alignment with the plan's phase
numbering — the same "don't rename/rebuild working, reviewed things just to match a
planning doc" policy Phase 15's PRD Out of Scope section already established. This
phase's actual diff is three small, genuinely-missing pieces: `.dockerignore` for both
images, a `Makefile` `build` target that was declared but had no recipe, and a
scheduled keep-alive workflow.

## 2. A scheduled workflow can't be live-tested before its own PR merges

**Context.** The PRD's first draft planned to verify the new `keep-alive.yml`'s
unset-variable skip path by actually triggering it via `workflow_dispatch` before
merging — the same "verify empirically, don't just read and assume" discipline this
project has applied since Phase 14. That plan hit a real GitHub constraint:
`workflow_dispatch` is only exposed for a workflow once its file exists on the
repository's *default* branch, not on an arbitrary feature branch — `gh workflow run`
against the pushed `feat/ci-containers` branch failed with a 404, "workflow not found
on the default branch."

**Decision.** Split the verification into what's actually possible at each point in
time: locally ran the exact shell script GitHub Actions would substitute (`${{ vars.
HEALTH_CHECK_URL }}` replaced with both an empty string and a real URL, matching
GitHub's own templating step) for both branches of the skip-vs-ping logic, catching
any real script bug before merge; the live on-GitHub `workflow_dispatch` trigger is
the first action taken immediately after this PR merges, not a step this phase could
have completed earlier no matter how it was sequenced. Corrected the PRD/FRD's
acceptance-criteria wording to describe this two-stage reality rather than a
verification method GitHub's own platform doesn't allow before merge — the same
"don't let the doc claim something that isn't literally true" standard Phase 15's
PRD/FRD correction (ADR 0015 §1) already set.
