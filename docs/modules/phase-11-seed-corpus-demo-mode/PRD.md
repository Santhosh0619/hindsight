# PRD: Seed Corpus & Demo Mode

## Problem

Every screen built through Phase 10 has been verified against small, hand-built
fixtures — a handful of services, one or two postmortems, an incident or two. That's
enough to prove each feature works, but it's not what a recruiter opening the deployed
URL sees: an empty workspace with nothing to click into. This phase builds the thing
that actually makes the product demoable — a realistic, synthetic corpus generated
once and committed to the repo, plus a one-click "try the live demo" path that puts a
visitor straight into that corpus with enough permission to run the platform's own
signature move (paste an alert, watch it investigate live) without ever signing up.

## Actors

- **Recruiter / demo visitor** — the actual audience for this phase. Clicks "Try the
  live demo" on the landing page, lands in a fully populated workspace, can browse
  everything, and can generate a brand-new brief against the real seeded corpus.
- **Santhosh (operator)** — runs `make seed` once against a fresh deployment to
  populate the demo workspace from the committed fixtures. Not a recurring action;
  idempotent if run again.

## Functional Requirements

- FR-01: `app/seed/` contains generator scripts (`generate_catalog.py`,
  `generate_postmortems.py`, `generate_incidents.py`, `generate_eval_cases.py`) whose
  output is committed as JSON fixtures — running `make seed` needs no LLM and no
  network access, and produces byte-identical data on every run.
- FR-02: The generated catalog has 40 services across 8 teams, a realistic tiered
  dependency graph, 3 shared hard dependencies, and 2 deliberate single points of
  failure.
- FR-03: The generated corpus has 80 postmortems spanning 3 years across the 12
  failure-mode families already established in `app/services/extraction/taxonomy.py`
  (ADR 0006 §1) — deliberately varying vocabulary across postmortems describing the
  same underlying failure, and including realistic mess (a wrong initial hypothesis,
  a partial mitigation, an incomplete action item) rather than tidy documents.
- FR-04: 12 demo incidents exist in the seeded workspace, 8 with a precomputed brief
  (`from_cache=true`) so the money screen renders content with zero LLM key
  configured.
- FR-05: 20 golden eval cases exist, each an alert text plus the postmortem ids a
  human (the generator, which knows its own ground truth) says are genuinely correct
  matches — ready for Phase 12's evaluation harness to consume.
- FR-06: `make seed` is idempotent — running it again against an already-seeded
  workspace makes no duplicate rows and doesn't error.
- FR-07: The landing page's existing "Try the live demo" button (built in Phase 3)
  logs a visitor into the seeded demo workspace with no signup step.
- FR-08: A demo guest can read every screen and can additionally create a new
  incident and generate a brief against the real seeded corpus — the platform's own
  demo moment — while remaining unable to modify the catalog, upload postmortems,
  manage members, or touch settings.
- FR-09: A demo guest's brief-generation is rate-limited, separately from the
  existing per-IP demo-session rate limit (which caps how many demo sessions can be
  created, not what an existing one can do).
- FR-10: A persistent banner is visible throughout the app for a demo session:
  "Demo workspace — synthetic data, read-only."

## User Stories

- As a recruiter with 90 seconds, I want to click one button and land in a workspace
  that already looks like a real, populated incident-intelligence tool, not an empty
  shell asking me to sign up first.
- As that same recruiter, I want to paste an alert and watch the actual six-node
  agent pipeline run against real data, not a canned screenshot.
- As Santhosh, I want the demo corpus to be honestly labeled synthetic everywhere a
  visitor might reasonably wonder whether it's real customer data.

## Out of Scope

- Regenerating the corpus on every `make seed` run — the generator scripts produce
  fixtures once, committed to the repo; `seed.py` only *loads* those fixtures, it
  doesn't regenerate them. Re-running the generators to produce different content is
  a deliberate manual action, not part of the seeding flow.
- Running seeded postmortems through the real (LLM-dependent) extraction agents —
  see FRD Gap #2 for why the generator emits extraction output directly instead.
- Phase 12's evaluation harness itself (running eval cases, computing recall@k/MRR) —
  this phase only produces the `EvalCase` rows Phase 12 will consume.
- Broader rate limiting (Phase 14's project-wide pass) — this phase adds exactly one
  narrowly-scoped limiter, for demo-guest brief generation, matching the precedent
  Phase 2 already set with `demo_signup_bucket`.

## Acceptance Criteria

Master-Prompt.md's phase checkpoint: **`make seed` from empty completes in under 5
minutes with no API key. Demo login works in one click. All 8 cached briefs render.**
Verified by running `make seed` against a genuinely empty dev database with
`LLM_API_KEY` unset, timing it, then logging in as a demo guest through the real UI
and opening each of the 8 pre-briefed incidents.
