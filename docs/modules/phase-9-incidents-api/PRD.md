# PRD: Incidents API + The Money Screen
Phase: 9
Module codes: B11 (`incidents`) from plan.md §6, plus F5 (New Incident), F6 (Incident
Detail), F7 (Incident List) from the frontend module map.

## Problem

Every phase since Phase 1 has built a piece of the pipeline — ingestion, retrieval,
correlation, synthesis, self-verification — but none of it has been reachable by a
person yet. This phase closes that gap: a responder pastes a raw alert, watches the six
agent nodes execute live, and gets back a brief with citations they can trust, a blast
radius that's actually computed from the service graph, and a place to say whether it
helped. Master-Prompt.md calls this "the money screen" for a reason — it's the single
screen a demo video lives or dies on, and the first point in the whole build where
everything before it becomes visible as one working product instead of eight separate
backend modules.

## Actors

- Any workspace member, browsing the incident list (F7) and reading incident detail
  (F6) — read access, no role gate.
- An owner or responder, filing a new incident and triggering brief generation (F5) —
  the same write-vs-read split established since Phase 2's RBAC model.
- Phase 8's compiled graph, invoked here for the first time by a real caller.
- Phase 12's evaluation harness, which will read `brief_feedback.correct_postmortem_id`
  as ground-truth signal once enough of it accumulates.

## Functional Requirements

FR-01: `POST /workspaces/{workspace_id}/incidents` creates an `Incident` from a title
and raw alert text (owner/responder only), independent of brief generation — filing an
incident and generating its first brief are two separate actions, so a responder can
create an incident from an alert and generate (or regenerate) a brief for it on demand.

FR-02: `GET /workspaces/{workspace_id}/incidents` lists incidents for the workspace,
filterable by `status`, `severity`, and `service_id` (matching an incident whose most
recent signal's `affected_service_ids` contains that service), cursor-paginated,
newest first — any member.

FR-03: `GET /workspaces/{workspace_id}/incidents/{id}` returns full incident detail —
any member. `PATCH .../incidents/{id}` updates `status` (and `title`) — owner/responder
only; transitioning to `resolved` or `false_positive` sets `resolved_at` automatically
if not already set.

FR-04: `POST .../incidents/{id}/brief` runs Phase 8's compiled graph against the
incident's `raw_alert_text` to completion and returns the resulting brief as JSON —
owner/responder only (an LLM-calling, state-mutating action). Every call is a genuinely
new run: brief `version` always increments, there is no implicit "reuse the last one."

FR-05: `GET .../incidents/{id}/brief/stream` runs the same underlying generation as
FR-04, but as a live Server-Sent Events stream of `node_start`/`node_end`/`retry`/`done`/
`error` events (Phase 8's `stream_graph_events`, wired to a real HTTP response for the
first time) — this is what F5's live pipeline visualization actually watches.

FR-06: `GET .../incidents/{id}/briefs` lists every brief version generated for an
incident, newest first — any member. Each brief's citations and matched postmortems are
returned enriched with real chunk `char_start`/`char_end` and postmortem summaries
(title/severity/date), not just the raw ids Phase 8's internal schemas carry, since the
UI needs those to actually render something a human can read.

FR-07: `POST .../incidents/{id}/brief/{brief_id}/feedback` records a verdict (helpful /
partially / unhelpful), optionally naming the correct postmortem and a free-text note —
any member (feedback is a judgment call, not a workspace-mutating write in the RBAC
sense, but gated the same as every other POST in this codebase for consistency).

FR-08: F5 (New Incident) provides a textarea prefilled with a realistic example alert
plus three one-click sample alerts, and on submit drives a live six-node visualization
(queued → running → done per node, a visible loop-back on retry) from the real SSE
stream — never a timer-faked animation — then renders the brief progressively as it
completes.

FR-09: F6 (Incident Detail) renders ranked hypotheses with confidence bars and inline
citation chips; matched prior postmortems with their correlator subscore breakdown
(not just a single score, so the ranking is legible); a blast radius panel; a runbook
with each step attributed to its source; a feedback control; and badges for
`from_cache`/`llm_used=false`/`correction_passes > 0` when relevant.

FR-10: F7 (Incident List) shows incidents filterable by status/severity/service,
paginated, each row linking into F6.

## User Stories

- As a responder, I want to paste an alert and watch the system actually work — not a
  spinner — so I trust the brief it produces enough to act on it during a real incident.
- As a responder reading a brief, I want to see *why* a prior incident matched (the
  subscore breakdown), not just a ranked list, so the match feels earned rather than
  magical.
- As a responder, I want a citation chip to show me the exact grounding text, not just
  claim one exists — closing the loop from "the model said so" to "here's the excerpt."
- As a responder who disagrees with a brief, I want to say so and name the right answer,
  so that judgment isn't lost — it becomes training signal for the eval harness later.
- As the author of Phase 12's evaluation harness, I want `brief_feedback` rows with
  `correct_postmortem_id` accumulating from real usage, not something invented later.

## Out of Scope

- F8 (Knowledge Base / postmortem detail page) — Phase 10. A citation chip's "see the
  source" affordance this phase shows the grounding excerpt inline (using the citation's
  own resolved chunk content plus `char_start`/`char_end` for highlighting), since the
  dedicated postmortem detail page this would otherwise deep-link to doesn't exist until
  next phase. Revisit as a real deep link once F8 ships.
- F4 (Dashboard) — Phase 10.
- Multi-turn follow-up questions against an existing incident's checkpointed state —
  Phase 8's checkpointer is wired in and used for every run this phase (thread id =
  incident id), but nothing in this phase's API sends a *second* turn through it; that's
  a later phase's concern once there's a documented reason to build it.
- Rate limiting brief generation beyond the existing RBAC gate — Phase 13/14.
- `eval_cases` population from accumulated feedback — Phase 12 reads
  `brief_feedback`, doesn't populate it automatically.

## Acceptance Criteria

1. Creating an incident and generating a brief for it, end to end, produces a real
   `IncidentBrief` with at least the deterministic content (blast radius, matched
   postmortems) populated even with no LLM configured (this build's actual environment).
2. The SSE stream emits six `node_start`/`node_end` pairs in order for a normal run, and
   a visible `retry` event when the critic's score forces a corrective loop.
3. Every citation returned by the API carries real `char_start`/`char_end` resolved from
   the actual chunk it names, not a placeholder.
4. `matched_postmortems` in the API response carries the full five-subscore breakdown
   per candidate, not a collapsed single score.
5. A viewer-role member can read F6/F7 and cannot see the "Generate brief" affordance or
   feedback controls (mirrors the RBAC pattern already proven in Phase 3).
6. Every incidents query is `workspace_id`-scoped; a member of workspace A never sees
   workspace B's incidents, briefs, or feedback regardless of endpoint.
7. F5's node visualization is verifiably driven by real SSE events (not a timer) —
   confirmed live in a browser, not just asserted from the code.
8. `ruff`, `mypy --strict`, `tsc`, `eslint`, and both backend and frontend test suites
   are all clean.
