# NFR: Documentation

## Quality

- Written to read as a human engineer's own account of their own project — direct,
  specific, no filler, no marketing-voice superlatives, no formulaic AI-writing tells
  (no "leverages cutting-edge," no emoji-per-bullet, no restating the section heading
  as the first sentence of its own paragraph). Explicit user instruction this phase:
  the README has to read as human-written, because the actual reader is a recruiter
  deciding whether to take the project seriously, and AI-sounding prose undermines
  that on sight.
- Every claim earns its place by being true and checkable, not by sounding impressive
  — the evaluation section reports a tied ablation result honestly (per plan.md §13's
  own explicit instruction) rather than reaching for a number that looks better, and
  the limitations section names real weaknesses instead of the usual token
  "still working on documentation" placeholder.

## Accuracy

- No number in any of the three documents is written from memory or copied from an
  earlier ADR without independent re-verification this phase — the evaluation table
  is a fresh harness run, the corpus size is a fresh fixture count, the tech-stack
  table is cross-checked against the current `pyproject.toml`/`package.json`.
- `docs/data-model.md` is grounded in the actual SQLAlchemy models, not plan.md's
  pre-implementation schema sketch — the two are expected to have diverged somewhat
  over 16 phases, and the doc's job is to reflect what's real.

## Constraints

- No application code, test, or CI changes — this phase's diff is `README.md` plus
  new files under `docs/`.
- No image, screenshot, GIF, or video anywhere in this phase's diff — confirmed scope
  decision, not an oversight to flag in review.
- No committed file uses interview/Q&A framing or is named/worded in a way that reads
  as interview preparation — `docs/design-notes.md` (local-only, gitignored) remains
  the only place that framing exists, and this phase doesn't touch it.
- Markdown only, consistent with every other doc in `docs/` — no new tooling, no
  static-site generator, no doc-build step.

## Maintainability

- `docs/architecture.md` and `docs/data-model.md` are written to need re-verification,
  not rewriting, the next time something drifts — structured so a future phase can
  diff "what the doc says" against "what `app/models/` actually has" without needing
  to reread the whole document to find the relevant section.
- README links to `docs/architecture.md`, `docs/data-model.md`, and
  `docs/decisions/` rather than duplicating their content — one place to update each
  fact, not three.
