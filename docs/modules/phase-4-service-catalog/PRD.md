# PRD: Service Catalog & Graph Traversal
Phase: 4
Module codes: B5 (`catalog`), B6 (`graph`) from plan.md §6

## Problem

Hindsight's entire value proposition depends on knowing how services depend on each
other — "checkout-api depends on payments-svc depends on the shared Postgres pool" is a
graph relationship that exists nowhere in the text of a postmortem. Before any of the
later retrieval/correlation/blast-radius features can exist, there needs to be a place
to record services, their ownership, and their dependency edges, and a way to traverse
that graph efficiently and correctly — including the one case every naive graph
traversal gets wrong: cycles.

## Actors

- A workspace owner/responder, populating the catalog by hand or via bulk import.
- Every later backend module that needs to answer "what does X depend on" or "what
  breaks if X goes down" — the correlator (B10), the incident brief (B11), and the
  Service Map UI (F9, Phase 10) all call straight into this phase's `GraphStore`.
- A `viewer`, who can read the catalog and traverse the graph but never mutate it.

## Functional Requirements

FR-01: Any workspace member can list/get services, teams, and edges, and traverse the
graph (upstream/downstream/blast-radius/shortest-path) — read access is not role-gated
beyond ordinary workspace membership.

FR-02: Only `owner`/`responder` can create, update, or delete teams, services, and
edges, and only they can bulk-import a catalog.

FR-03: Creating a service edge rejects a self-edge (`from_service_id ==
to_service_id`) and a duplicate `(from, to, kind)` triple — the latter is already a DB
uniqueness constraint from Phase 1; this phase surfaces it as a clean `409`, not a raw
integrity-error 500.

FR-04: `POST /catalog/import` accepts a JSON payload of teams, services, and edges in
one call and creates them transactionally — either the whole import succeeds or none
of it does. Edges referencing a service by name (not yet knowing its generated UUID)
are resolved within the same import, so a fixture can describe a whole graph in one
shot without two round-trips.

FR-05: `GraphStore` (a `Protocol`) exposes `upstream`, `downstream`, `neighborhood`,
`blast_radius`, and `shortest_path`, each `workspace_id`-scoped and depth-capped
(default 4, caller-configurable). `PostgresGraphStore` implements it with recursive
CTEs that are cycle-safe by construction — a diamond dependency (two paths converging
on the same downstream service) is counted once, and an actual cycle in the data
terminates instead of looping forever.

FR-06: Blast radius returns each reached service with a numeric score derived from
path length, edge criticality (`hard` propagates further/scores higher than `soft`),
and the reached service's tier, plus the actual path that reached it — so a caller
(eventually the UI) can explain *why* a service is in the radius, not just that it is.

FR-07: `GET /catalog/graph` returns the full node/edge set for the current workspace in
a shape a graph-visualization UI can consume directly (Phase 10's Service Map) —
though this phase ships no UI itself.

## User Stories

- As a responder investigating an incident, I want to ask "what's downstream of
  checkout-api" and get a correctly ordered, explained answer, even if the dependency
  graph has cycles or diamonds.
- As a workspace owner setting up a new workspace, I want to import my whole service
  catalog from a JSON file in one call instead of clicking through a form forty times.
- As a `viewer`, I want to browse the catalog and traverse the graph without being able
  to change anything.
- As the author of a later module (correlator, brief generation, Service Map UI), I
  want a stable `GraphStore` protocol so I never write my own recursive CTE.

## Out of Scope

- The Service Map UI itself (F9) — Phase 10.
- CSV import (FR-04 only requires JSON this phase; CSV parsing is a thin addition
  layered on the same import path later if ever needed — not blocking anything).
- Any use of the graph by the correlator/agent pipeline (B10) — those are Phases 6-8;
  this phase only builds the `GraphStore` they'll depend on.

## Acceptance Criteria

1. Import a ~10-service fixture (with at least one diamond and one deliberate cycle),
   query blast radius from a service near the top, and get a correctly ordered result
   — the diamond-shared service appears once, the cycle doesn't hang the request.
2. `hard`-criticality edges produce a higher blast-radius score than `soft` ones at the
   same depth; depth-capping is respected (a service five hops away is excluded at
   `depth=4`).
3. A `viewer` gets 403 on every catalog-mutating endpoint; every endpoint is
   `workspace_id`-scoped (a member of workspace A gets 404 on workspace B's catalog).
4. `ruff`, `mypy --strict`, and `pytest` are all clean.
