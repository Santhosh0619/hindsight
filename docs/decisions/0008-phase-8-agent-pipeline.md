# ADR 0008: LangGraph Agent Pipeline — State Design, Degradation, and a Real Concurrency Bug

## 1. Three `TriageState` keys beyond Master-Prompt.md's literal field list

**Context.** Master-Prompt.md names `TriageState`'s fields explicitly: `incident_id,
workspace_id, raw_text, signal, retrieval, candidates, draft, verification, final,
retry_count, trace, messages`. Nothing in that list has anywhere to hold
`correlator_node`'s own described output ("blast radius via `GraphStore`"), nor any way
for `critic_node`/`briefer_node`/`route_after_critic` to know whether a given node
degraded because no LLM was reachable versus an LLM ran and simply produced nothing.

**Decision.** Added `blast_radius`, `llm_used`, and `from_cache` to `TriageState`,
same class of gap-filling as Phase 6's un-named 12-family taxonomy — the plan describes
the behavior without naming every field it requires, and this phase's own documented
judgment fills the gap rather than contorting the described behavior to fit an
incomplete literal list. `llm_used` specifically exists because "the draft is empty" is
ambiguous on its own: it could mean no LLM was ever reachable, or it could mean the LLM
ran and had nothing to say. `route_after_critic` needs to tell these apart to decide
whether retrying is worth anything at all.

## 2. `failure_mode_overlap` without ever classifying the incident's own failure mode

**Context.** `correlator_node` must run with no LLM call, but Phase 6's
`classify_failure_modes` — the only thing in this codebase that assigns a failure-mode
family to anything — is itself an LLM call, and it classifies postmortems, not raw
alert text. There is no deterministic way to know "what failure mode is this incident"
without either calling an LLM (forbidden here) or inventing a rule-based classifier
(a much bigger, riskier piece of new logic than this subscore warrants).

**Decision.** Reframed as a recurrence signal among the retrieved candidates
themselves, not a comparison against the incident: for every failure-mode label present
across the whole candidate set, compute its frequency (fraction of candidates carrying
it); a candidate's `failure_mode_overlap` is the mean frequency of its own labels. A
candidate whose failure modes are common among the *other* retrieved candidates scores
higher — "the rest of what retrieval found agrees this kind of failure is the pattern
here." This is exactly what plan.md's "recurrence detection" bullet describes, and it's
fully deterministic and unit-testable against hand-built fixtures (`test_correlator.py`)
with zero network access, matching `correlator_node`'s "no LLM" contract without needing
a rule-based classifier that would itself need its own validation story.

## 3. `critic_node`'s deterministic gate operates only on what the analyst actually saw

**Context.** FR-05 requires citation validation to check "does `chunk_id` exist in the
retrieval set" — but a postmortem's chunks in the database and the chunks actually shown
to `analyst_node` in its prompt (one excerpt per retrieved result, via `chunk_excerpt`)
are different sets. A citation naming a real chunk from the right postmortem that
happened not to be the one excerpted would pass a naive "does this chunk_id exist in the
DB" check while still being ungrounded — the model couldn't have legitimately cited
content it never saw.

**Decision.** The valid-citation set is `{chunk_excerpt.chunk_id for every result in
retrieval.results with a chunk_excerpt}` — narrower than "every chunk that postmortem
owns," exactly as wide as what the prompt actually contained. Paired with a deliberately
crude plausibility check (does at least one length-≥4 word token from the claim appear
in the cited chunk's content) that exists to catch obviously-wrong citations cheaply,
not to replace the LLM judge that runs afterward on whatever survives. `test_citation_
check.py` proves both failure modes independently: a chunk_id outside the retrieval set
always fails regardless of content, and a real chunk_id with no term overlap also fails.

## 4. A real concurrency bug, caught only by running a real graph through the real streaming wrapper

**Context.** `stream_graph_events` wraps `graph.astream_events(...)`, consuming events
in a loop and writing an `AgentRunStep` row on each node's `on_chain_end`. The first
draft used the same `AsyncSession` for those writes as the one bound into the graph's
own nodes (via `partial(node_fn, db=db, ...)` in `build_graph`).

**Decision (forced by an actual failure, not anticipated by design review).** Running
`test_streaming.py`'s first version against a real graph produced `sqlalchemy.exc.
InterfaceError: This session is provisioning a new connection; concurrent operations
are not permitted` the moment `retriever_node` started — `astream_events` runs the
compiled graph as its own concurrent task while the consuming generator's body executes
independently, so the observer loop's `db.commit()` for the *previous* node's step row
raced against the *next* node's own queries on the same session. This is the same
underlying class of bug as ADR 0007 §1 (Phase 7's concurrent retrievers needing their
own sessions), here between an external observer and the graph run instead of between
sibling retrievers within one node. Fixed by giving every `AgentRunStep` write its own
fresh session via `get_session_factory()`, never touching whatever session the graph's
nodes are bound to. Two independent code-reviewer passes on the *design* (FRD read
alone) did not catch this — only actually executing `stream_graph_events` against a
compiled graph did. The lesson repeats across three phases now: a concurrency argument
written in a comment or a doc is a claim, not a proof, until something has actually run
concurrently and not broken.

## 5. `analyst_node` is the semantic cache's real first consumer, as ADR 0006 §2 predicted

**Context.** Phase 6 built `app/services/llm/cache.py` (exact-hash-then-cosine, scoped
by `workspace_id`+`purpose`) but deliberately left it unwired, naming Phase 8's brief
generation as its intended consumer per plan.md §10's documented degradation ladder
("quota exhausted → cached briefs for seeded incidents").

**Decision.** `analyst_node` checks the cache (`purpose="analyst_brief"`) before ever
calling the router, using the exact rendered prompt text as the cache key — a
near-duplicate *incident* prompt reusing a cached `DraftBrief` is precisely the
documented use case, unlike Phase 6's own per-postmortem extraction where a
near-duplicate prompt returning a different postmortem's facts would have been wrong.
`from_cache` propagates through to the persisted `Brief` row exactly as plan.md's
degradation levels require, so the UI (Phase 9+) can show an honest "served from cache"
badge rather than implying a live generation happened.

## 6. The checkpointer is built and verified this phase, but not wired into the running app

**Context.** Master-Prompt.md says the compiled graph happens "once at startup," which
could be read as instructing `app/main.py`'s lifespan to hold a live `AsyncPostgresSaver`
open for the whole app's lifetime.

**Decision.** Reconsidered before writing any node code (see the FRD's own note):
`AsyncPostgresSaver.from_conn_string` is an async context manager, and this graph has no
real caller yet — Phase 9's incidents API doesn't exist. Wiring it into `app/main.py`
now would add a second Postgres connection pool and a `setup()` round-trip to every test
that boots the app via the ASGI test client, for zero present benefit — the same
restraint this codebase already applied to the LLM router's lazy provider construction
and to leaving the semantic cache unwired until Phase 6 had nothing to point it at.
`build_graph`/`checkpointer_conn_string` are fully built, live-verified against this
project's real dev Postgres (`test_checkpointer.py` builds a real saver, runs a real
graph through it, and reads the persisted checkpoint back), and ready for Phase 9 to
wire into the app's actual startup once there's a request path that needs it.
