# PRD: Evaluation Harness

Phase: 12
Module codes: B14 / F11 (from plan.md §6)

## Problem

Every retrieval and agent-pipeline claim made so far (Phases 6-11) has been verified by
hand — a curl walkthrough, a live browser session, a manually-inspected precomputed
brief. That proves the pipeline runs; it proves nothing about whether it finds the
*right* prior postmortem, and it produces no number a README can cite. plan.md §13 is
explicit that reporting real recall/MRR/groundedness numbers is what meaningfully sets
this apart — almost no portfolio RAG project does this. This module builds the harness that produces those numbers, against
the 20 golden eval cases Phase 11 already seeded, and makes the three-way ablation
(vector / vector+BM25 / vector+BM25+graph) a repeatable, first-class command rather than
a one-off script.

## Actors

- **Operator (Santhosh)** — runs `make eval MODE=<mode>` from the CLI to produce a run
  and its metrics; pastes the resulting ablation table into the README.
- **Workspace member (any role)** — reads past run results and the ablation table on the
  F11 Evaluation page. Read-only; no role can trigger a run from the UI (see Out of
  Scope).

## Functional Requirements

FR-01: `app/services/evaluation/metrics.py` provides pure, unit-testable functions for
recall@1, recall@5, MRR contribution, and deterministic citation validity. None of these
call an LLM.

FR-02: `app/services/evaluation/runner.py` runs every `EvalCase` row in a workspace
through one retrieval-ablation mode (`vector`, `vector_bm25`, or `full`), computes
per-case and aggregate metrics, and persists one `EvalRun` row plus one
`EvalCaseResult` row per case.

FR-03: The ablation modes compose Phase 7's existing retrieval primitives
(`search_vector`, `search_keyword`, `search_graph`, `reciprocal_rank_fusion`) directly —
`vector` uses vector search alone, `vector_bm25` fuses vector + keyword, `full` fuses
all three (vector + keyword + graph). This is the same retrieval math the live search
API and agent pipeline already use, not a reimplementation.

FR-04: Citation validity is computed deterministically per case (FR-01) against a
minimal draft brief derived from the top-retrieved postmortem's own extracted facts —
it does not require an LLM call, matching Master-Prompt.md's own description of it as
"deterministic."

FR-05: Groundedness is computed by an LLM judge (reusing Phase 8's
`judge_verification`) only when `settings.llm_configured`. Without a key, groundedness
is `None` for every case and the aggregate, and the CLI/UI say so plainly rather than
showing a zero or a fabricated number.

FR-06: `app/services/evaluation/cli.py` is `make eval`'s real target. `--mode
vector|vector_bm25|full` runs one mode and prints its metrics plus a per-case
drill-down highlighting failures first. `--mode all` (the default) runs all three modes
in sequence and prints the ablation comparison table plus a ready-to-paste Markdown
block.

FR-07: `GET /workspaces/{workspace_id}/evaluation/runs` returns recent `EvalRun` rows
(for the F11 trend chart and ablation table) to any authenticated workspace member.

FR-08: `GET /workspaces/{workspace_id}/evaluation/runs/{run_id}` returns one run's
metrics plus its per-case results (for F11's drill-down) to any authenticated workspace
member.

FR-09: F11 Evaluation page renders current metrics as cards, a trend chart of recall@5
and MRR across past runs, an ablation comparison table (most recent run per mode side by
side), and a per-case drill-down table with failing cases sorted first.

## User Stories

As the operator, I want to run `make eval MODE=all` and get real recall/MRR numbers
across three retrieval configurations, so that I can paste an honest ablation table into
the README and answer plan.md §17 Q5 with actual evidence instead of a claim.

As a workspace member, I want to open the Evaluation page and see which specific eval
cases are failing and why, so that failure cases are visible rather than buried under an
aggregate score.

## Out of Scope

- Triggering a new eval run from the UI. Running the harness is an operator action
  (`make eval`), the same way `make seed` is — not a request-handler action, and an LLM
  call (groundedness) must never run inside a request handler per CLAUDE.md.
- Per-run diffing/regression alerts between runs. The trend chart shows history; nothing
  automatically flags a regression.
- Modifying `EvalCase` rows from the UI (create/edit/delete golden cases). Cases are
  authored by the seed generator (Phase 11); this phase only reads and scores them.

## Acceptance Criteria

- `make eval MODE=all` completes against the real seeded corpus with no LLM key
  configured, producing three `EvalRun` rows (one per mode) with populated
  recall@1/recall@5/mrr/citation_validity and `groundedness=None`, and prints a
  Markdown ablation table.
- The three modes are measured independently against the real 20-case corpus and
  genuinely reflect what each retriever contributes — including reporting honestly if
  two modes tie, rather than assuming ahead of time that they must differ. (They did
  tie in this build: see ADR 0012 for why, and plan.md §13's own instruction to report
  a negative ablation result honestly.)
- F11 renders real data from the endpoints above against the real dev stack: cards,
  trend chart, ablation table, and a drill-down that surfaces failing cases first.
