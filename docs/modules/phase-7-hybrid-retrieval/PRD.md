# PRD: Hybrid Retrieval
Phase: 7
Module codes: B9 (`retrieval`) from plan.md §6, plus F10 (`Search`) from the frontend
module map.

## Problem

A single retrieval strategy always has a blind spot. Pure vector search misses exact
error codes and identifiers — an embedding model treats `"ORA-12520"` as just another
token, not a precise signal, so a semantically-similar-but-wrong postmortem can
outrank the one that actually contains that code. Pure keyword search misses
conceptually related postmortems that never use the same words — "checkout timed out"
and "payment gateway unresponsive" can describe the same failure mode without sharing
vocabulary. And neither captures the structural signal this project's own service
catalog and graph already encode: a postmortem about a service's direct neighbor is
more likely relevant to an incident on that service than plain text similarity alone
would ever surface. Hindsight's whole pitch is that combining these three signals
retrieves better than any one alone — this phase is where that claim becomes real,
testable code instead of an assertion in a README.

## Actors

- Any workspace member, searching the knowledge base via F10.
- Every later backend module that needs retrieval (the LangGraph pipeline's retriever
  node in Phase 8, the correlator that follows it) — this phase's `hybrid_search`
  function is the shared entry point they call, not a per-phase reimplementation.
- The evaluation harness (Phase 12), which needs `mode=vector|keyword|graph|hybrid` to
  run the ablation study plan.md §13 requires (recall@k per mode, to prove hybrid
  actually beats each mode alone — not just assert it).

## Functional Requirements

FR-01: `GET /workspaces/{workspace_id}/search?q=&mode=` accepts a free-text query and
a retrieval mode (`hybrid` default, or `vector`/`keyword`/`graph` alone), returning
ranked postmortems with supporting chunk excerpts, graph reasoning (when applicable),
and — critically — which retriever(s) surfaced each result, so both the UI and the
Phase 12 ablation study can attribute a hit to its source.

FR-02: Vector retrieval embeds the query (reusing Phase 5's local `embed()`, no LLM
call) and ranks postmortem chunks by pgvector cosine distance, workspace-scoped, capped
by both a top-k limit and a maximum-distance threshold — a query with nothing
meaningfully close in the corpus returns fewer results, not top-k worth of noise.

FR-03: Keyword retrieval ranks postmortem chunks by Postgres `ts_rank_cd` over the
existing `tsv` column, then reranks that candidate set with `rank_bm25` for a second,
independent relevance signal — catches exact error strings/codes that an embedding
represents badly, per the checkpoint's explicit test case.

FR-04: Graph retrieval matches the query text against the workspace's actual service
names (Phase 4's catalog); for each match, expands to its k=2 neighborhood via the
existing `GraphStore` protocol (no new graph logic — this phase is a consumer of
Phase 4's traversal, not a reimplementation), then surfaces postmortems linked
(`postmortem_services`) to any service in that expanded set, weighted by link role
(`root_cause` > `affected` > `downstream`, matching Phase 6's existing role values) and
recency.

FR-05: `mode=hybrid` runs all three retrievers concurrently (`asyncio.gather`, not
sequentially) and fuses their independently-ranked postmortem lists via Reciprocal
Rank Fusion (`score = Σ 1/(k + rank_i)`, `k` from `Settings.rrf_k`, already defined
since Phase 1 and unused until now). Every result's `source_attribution` records which
retriever(s) contributed to it and at what rank, not just the final fused score — the
UI's whole value proposition (F10) is showing this, not hiding it behind one number.

FR-06: `mode=vector`/`mode=keyword`/`mode=graph` run exactly one retriever and skip
fusion entirely (a single ranked list needs no combining) — this is what makes the
mode parameter usable for Phase 12's ablation study: comparing hybrid's recall against
each mode alone requires each mode to be independently queryable, not simulated by
zeroing out weights in a fused result.

FR-07: F10 (Search) provides a text input, a mode toggle (hybrid/vector/keyword/graph),
and a result list where each result shows a colored chip per contributing retriever —
the single clearest visual demonstration in this project that hybrid retrieval is
real, not asserted (plan.md §6's own framing of why F10 matters for a portfolio).

## User Stories

- As a responder searching for "connection pool exhausted", I want a semantically
  similar postmortem to surface even if it says "ran out of DB connections" instead —
  vector retrieval, not keyword matching, is what finds this.
- As a responder who has an exact error code from a stack trace, I want that precise
  string to retrieve the postmortem that actually contains it, not get buried under
  semantically-similar-but-wrong results — keyword retrieval's job.
- As a responder investigating an incident on `checkout-api`, I want postmortems about
  its direct dependencies to surface even if they never mention `checkout-api` by
  name — graph retrieval's job.
- As the author of Phase 8's agent pipeline, I want one `hybrid_search` function that
  already solved "run three things concurrently and fuse them," so the retriever node
  is a thin wrapper, not a reimplementation.
- As the author of Phase 12's evaluation harness, I want `mode=vector|keyword|graph` to
  produce genuinely independent single-source results, so an ablation study measuring
  "how much does hybrid actually help" is measuring something real.

## Out of Scope

- The LangGraph pipeline itself (normalizer/retriever/correlator/analyst/critic nodes)
  — Phase 8. This phase builds the retrieval function that Phase 8's retriever node
  will call; it does not build the node or the graph.
- Query understanding / intent classification — the query is used as-is for embedding
  and as-is (through `websearch_to_tsquery`) for keyword matching; no LLM-based query
  rewriting this phase.
- Incident-signal-driven retrieval (candidate services derived from an incident's
  extracted symptoms) — Phase 8/9's concern. This phase's graph retrieval derives
  candidate services from matching the raw query text against service names directly.
- Pagination of search results — a single top-k ranked list per request, matching the
  FRD's endpoint shape; no cursor parameter this phase.

## Acceptance Criteria

1. A query using vocabulary absent from the target postmortem's text still retrieves
   it in `mode=vector` (and in `mode=hybrid`) via semantic similarity.
2. A query containing an exact error code/string retrieves the postmortem containing
   that exact string in `mode=keyword` (and in `mode=hybrid`), even if it wouldn't
   rank highly by vector similarity alone.
3. A query naming a real service in the catalog retrieves postmortems linked to that
   service's k=2 neighborhood in `mode=graph` (and in `mode=hybrid`), even for
   postmortems that never mention the queried service by name.
4. The three modes return visibly different result sets for the same query on a
   fixture designed to exercise all three signals — not the same list with reordered
   scores.
5. Every result in `mode=hybrid` carries `source_attribution` naming which retriever(s)
   actually contributed to it; a result found by only one retriever shows only that
   one, never invented attribution.
6. Every retrieval query is `workspace_id`-scoped; a member of workspace A searching
   never sees workspace B's postmortems regardless of mode.
7. F10 renders the mode toggle, the query input, and a colored chip per contributing
   retriever on each result, verified live in a browser (not just via the API).
8. `ruff`, `mypy --strict`, `tsc`, `eslint`, and both backend and frontend test suites
   are all clean.
