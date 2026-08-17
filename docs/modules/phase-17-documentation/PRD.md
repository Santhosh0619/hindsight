# PRD: Documentation

Phase: 17
Module codes: cross-cutting — no new B<X>/F<X> row in plan.md §6. No application code
changes; this phase's output is entirely `README.md` and `docs/`.

## Problem

Hindsight has been built for 16 phases with real evaluation numbers, a working
corrective-RAG pipeline, and 16 ADRs recording every non-obvious design decision — but
the README is still Phase 1's four-line stub, and there is no architecture or data-model
document a reader could actually go find. The person this phase is really for is a
recruiter or hiring manager who clicks through from a resume or LinkedIn post, spends
90 seconds on the README, and decides in that window whether the project is worth a
second look. That reader doesn't read `docs/decisions/`, doesn't run the code, and
won't dig for the evaluation numbers — if the README doesn't make the case, nothing
else in the repo gets the chance to.

Two scope decisions were made with the user before writing anything, because
Master-Prompt.md's Phase 17 spec conflicts with standing project decisions:

1. **No images or video in this phase.** Master-Prompt.md's README order calls for a
   hero screenshot above the fold and one screenshot per feature bullet, plus a
   `docs/screenshots/` folder. The project's standing decision (confirmed again this
   phase) is that all screenshot/recording capture happens in one session after Phase
   18, not per-phase. This phase ships text-only; the image/video pass is a separate,
   later piece of work, not silently dropped.
2. **No `docs/interview-prep.md`.** Master-Prompt.md's Phase 17 also calls for
   consolidating plan.md §17's 12 technical defense questions into a committed
   `docs/interview-prep.md`. That file was already renamed to `docs/design-notes.md`
   and made local-only/gitignored earlier in the project specifically so the public
   repo carries no evidence of interview preparation — confirmed again this phase, not
   reopened. The 12 questions' actual substance (one-database rationale, RRF, the
   corrective loop, the honest tied-ablation result, the system's real weaknesses) is
   genuine architecture content, so it's covered inside `README.md` and
   `docs/architecture.md` as ordinary documentation prose — no Q&A framing, no
   committed file that reads as interview scaffolding.

## Actors

- **A recruiter or hiring manager**, cold, no context — the primary reader `README.md`
  is written for. Everything above the fold has to work for someone who has never
  heard of this project and will not scroll past a wall of unearned jargon.
- **A senior engineer doing technical due diligence** — the reader `docs/architecture.md`
  and `docs/data-model.md` are for, someone who wants the real schema and the real
  reasoning, not marketing language.
- **A future contributor (including a future version of the assistant building later
  phases)** — the reader every ADR has been written for all along; this phase doesn't
  change that, `docs/decisions/` stays as-is.

## Functional Requirements

FR-01: `README.md` is rewritten in full, following Master-Prompt.md's Phase 17
ordering with images/video removed per the scope decision above: title + one-line
pitch, the 2am-scenario problem statement, what it does, the evaluation table with
real measured numbers, architecture, the agent pipeline, tech stack, quick start,
limitations, project structure/roadmap/license.

FR-02: `docs/architecture.md` covers the system diagram, the one-database rationale
(with the explicit "here's the number at which I'd switch to Neo4j" framing plan.md
asks for), and the agent pipeline in more depth than the README has room for — written
for a reader who wants to evaluate the engineering, not be sold on it.

FR-03: `docs/data-model.md` documents the real schema as implemented — every table,
its real columns, and the indexes that matter — read from the actual SQLAlchemy
models and Alembic migrations, not transcribed from plan.md's original (pre-
implementation) projected design, since 16 phases of real implementation work is
enough distance for drift to have happened.

FR-04: Every number, command, and claim in all three documents is verified against
the running system or the actual codebase before being written down — the evaluation
table is a fresh run of the real harness (not copied from an old ADR), the quick-start
commands are checked against the actual `Makefile`/`.env.example`, and the corpus size
numbers are counted from the actual seed fixtures.

## User Stories

As a recruiter skimming this repo for 90 seconds, I want the README's first screen to
tell me what problem this solves and why it's hard, so I don't bounce before reaching
the parts that show real engineering depth.

As a senior engineer doing due diligence, I want the real evaluation numbers and an
honest account of where the system is weak, so the project reads as credible
self-assessment rather than a sales pitch.

As a future contributor, I want the architecture and data-model docs to match what the
code actually does today, so they're still trustworthy after 16 phases of drift from
the original plan.

## Out of Scope

- Any image, screenshot, GIF, or video — deferred to the dedicated post-Phase-18
  capture session per the project's standing decision (see Problem).
- A committed, Q&A-framed interview-prep document — the local `docs/design-notes.md`
  already serves that purpose privately; this phase folds the substance into public
  docs without the framing, not a second copy of the same content.
- Rewriting or reorganizing `docs/decisions/` — 16 ADRs already exist and are already
  the record this project relies on; this phase links to them, it doesn't rewrite them.
- Any application code, test, or CI change — this phase is text only.

## Acceptance Criteria

- `README.md` reads correctly top-to-bottom with no image/video reference left as a
  placeholder or broken link — this phase's own scope decision is text-only, not
  text-with-gaps.
- Every number quoted (evaluation metrics, corpus size, phase count) is traceable to a
  command actually run or a file actually read during this phase, not carried over
  from memory or an old document without re-checking.
- The quick-start section's three commands are checked against the current
  `Makefile`/`.env.example`/`docker-compose.yml` and correctly describe what happens
  when they're run.
- No file in this phase's diff uses interview/Q&A framing, and none is named or worded
  in a way that reads as interview preparation.
