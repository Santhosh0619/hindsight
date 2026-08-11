# Skill: document-writer — Step 4 of Every Module

## Purpose
Write PRD, FRD, NFR before any code. These are the source of truth that the
code-reviewer sub-agent checks against. Code that does not match these docs fails review.

## Directory
docs/modules/<module-name>/
  PRD.md
  FRD.md
  NFR.md

## Commit after writing, before coding
```bash
git add docs/modules/<module-name>/
git commit -m "docs(phase-N): add PRD, FRD, NFR for <module name>"
```
Do not write any application code until this commit is done.

---

## PRD.md template
```
# PRD: <Module Name>
Phase: N
Module codes: B<N> / F<N> (from plan.md §6)

## Problem
One paragraph: what pain or need does this module address?

## Actors
Who uses this module? (end user, API client, background worker, agent, admin)

## Functional Requirements
FR-01: <observable behaviour>
FR-02: ...

## User Stories
As a <actor>, I want <capability>, so that <outcome>.

## Out of Scope
What this module explicitly does NOT do.

## Acceptance Criteria
How we confirm the module works correctly end-to-end.
```

## FRD.md template
```
# FRD: <Module Name>

## API Endpoints (Backend — FastAPI)
For each endpoint:
  Method + Path:
  Auth required: yes/no, role:
  Request schema (Pydantic model):
  Response schema (Pydantic model):
  Error codes:

## React Components (Frontend)
For each page/component:
  Component name + file path:
  Props interface:
  API calls made:
  States managed:
  User interactions:

## Data Model Changes
New or changed tables, columns, indexes.
Reference plan.md §8. State deviations with reasons.

## Internal Architecture
Key services, functions, their responsibilities.

## Dependencies
What this module calls. What calls this module.

## Sequence Flows
Text-based sequence diagrams for non-trivial flows.

## Edge Cases & Error Handling
Named edge case → how handled.
```

## NFR.md template
```
# NFR: <Module Name>

## Performance
Latency targets. Expected load. Caching if any.

## Security
Auth enforcement point. Input validation. Tenant isolation. Secret handling.

## Reliability
Graceful degradation when a dependency is unavailable.

## Observability
What is logged (structlog). What metrics. What traces.

## Testability
Backend: what is unit tested, what is integration tested, mock boundaries.
Frontend: what is component tested, what is e2e tested.
E2E: which user journeys are covered for this module.

## Constraints
Hard constraints from plan.md that apply here.
```
