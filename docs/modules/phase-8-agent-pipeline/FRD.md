# FRD: LangGraph Agent Pipeline

No API endpoints or React components this phase (see PRD Out of Scope) — this FRD is
entirely internal architecture.

## Gaps this phase had to resolve (Master-Prompt.md/plan.md underspecify these)

Same class of gap as Phase 6's un-named 12-family taxonomy and Phase 7's uncalibrated
distance threshold — the plan names the shape but leaves the wiring to this phase's own
documented judgment:

1. **Naming collision**: `app.models.incident.IncidentSignal` (the Phase 1 DB model) and
   the agent's structured-output type Master-Prompt.md also calls `IncidentSignal` can't
   share a name in the same import graph. The agent's raw output type is
   `IncidentSignalOut` (`app/schemas/incident.py`), matching this project's existing
   `*Out` convention for schema types that cross a boundary; `normalizer_node` resolves
   it into `NormalizedSignal` (adds `affected_service_ids`/`unresolved_mentions`) before
   putting it on `TriageState["signal"]` and persisting the DB row.
2. **`TriageState` needs three keys beyond Master-Prompt.md's literal list**
   (`incident_id, workspace_id, raw_text, signal, retrieval, candidates, draft,
   verification, final, retry_count, trace, messages`): `blast_radius` (correlator's own
   described output — "blast radius via `GraphStore`" — has nowhere else to live),
   `llm_used` (needed by both `critic_node`, to skip its LLM stage, and `briefer_node`,
   to persist `brief.llm_used`; deriving it after the fact from whether `draft` is empty
   would conflate "no LLM" with "LLM ran and found nothing"), and `from_cache` (same
   reasoning — `briefs.from_cache` needs a source, and "was this draft served from
   `semantic_cache`" isn't recoverable from any other field). All three default to a
   falsy/empty value and are set by the node that actually produces them.
3. **`failure_mode_overlap` cannot compare the incident to a failure mode it was never
   classified into** — nothing in this pipeline runs Phase 6's `classify_failure_modes`
   against the incident itself (that agent classifies *postmortems*, not alerts, and
   running a fourth LLM call here would violate `correlator_node`'s "no LLM" contract
   outright). Resolved as a **recurrence signal among the candidates themselves**: for
   each failure-mode label present across the whole candidate set, compute its
   frequency (fraction of candidates carrying it); a candidate's `failure_mode_overlap`
   is the mean frequency of *its own* failure-mode labels. A candidate whose failure
   modes are also common among the other retrieved candidates scores higher — "this
   looks like the kind of failure the rest of the retrieved set agrees on" — which is
   exactly what plan.md's "recurrence detection" bullet describes, without needing the
   incident to have its own failure-mode classification at all.
4. **`recency_weight` already exists, privately, in Phase 7's `graph.py`.** Rather than
   reimplementing the same 180-day linear decay floored at 0.2 a second time (risking
   drift between the two), `app/services/retrieval/graph.py`'s `_recency_weight` is
   promoted to a public `recency_weight` and imported directly by `correlator_node` — a
   minimal, justified refactor of already-reviewed Phase 7 code, not new logic.
5. **The semantic cache's actual consumer, deferred since Phase 6, is here.** ADR 0006
   §2 named this explicitly: `analyst_node`'s draft-generation call is wrapped by
   `app/services/llm/cache.py` (`purpose="analyst_brief"`), which is plan.md §10's
   documented degradation level 2 ("quota exhausted → cached briefs") — a near-duplicate
   *incident* prompt reusing a cached `DraftBrief` is exactly this cache's intended use
   case, unlike Phase 6's per-postmortem extraction where it would have been wrong.

## `app/agents/state.py`

```python
class TraceEntry(BaseModel):
    node: str
    note: str

class TriageState(TypedDict):
    incident_id: uuid.UUID
    workspace_id: uuid.UUID
    raw_text: str
    signal: NormalizedSignal | None
    retrieval: SearchResponseOut | None       # Phase 7's own response schema, reused as-is
    candidates: list[CandidateMatch]
    blast_radius: BlastRadius | None          # Phase 4's own schema, reused as-is
    draft: DraftBrief | None
    verification: VerificationResult | None
    final: IncidentBrief | None
    retry_count: int
    llm_used: bool                            # starts True; any LLMUnavailableError catch sets False
    from_cache: bool                          # set True only by a semantic-cache hit
    trace: list[TraceEntry]                   # one entry per node, human-readable, for tests/debugging
    messages: list[dict[str, str]]            # short {"role","content"} breadcrumbs, agent-memory seed
```

`SearchResponseOut` (`app/schemas/search.py`) and `BlastRadius` (`app/services/graph_store.py`)
are reused directly rather than re-declared — one schema per concept, not a parallel copy.

## `app/schemas/incident.py` (new)

```python
class IncidentSignalOut(BaseModel):        # raw pydantic-ai agent output
    symptoms: list[str]
    error_strings: list[str]
    metrics: dict[str, float]
    candidate_service_names: list[str]      # unresolved -- normalizer_node matches these
    time_window: TimeWindowOut | None
    severity_guess: Severity | None         # reuses app.models.postmortem.Severity
    extraction_confidence: float | None

class TimeWindowOut(BaseModel):
    start: datetime | None
    end: datetime | None
    description: str | None                 # e.g. "started ~14:00 UTC", kept when start/end are None

class NormalizedSignal(BaseModel):          # signal after service-name resolution
    symptoms: list[str]
    error_strings: list[str]
    metrics: dict[str, float]
    affected_service_ids: list[uuid.UUID]
    unresolved_mentions: list[str]
    time_window: TimeWindowOut | None
    severity_guess: Severity | None
    extracted_by_model: str | None
    extraction_confidence: float | None

class CandidateMatch(BaseModel):
    postmortem_id: uuid.UUID
    vector_score: float                     # 1 - cosine distance; 0.0 if not a vector hit
    keyword_score: float                    # raw_bm25 / (raw_bm25 + 1); 0.0 if not a keyword hit
    graph_score: float                      # raw graph-source score as-is; 0.0 if not a graph hit
    failure_mode_overlap: float             # mean frequency of this candidate's own failure-mode
                                             # labels across the whole candidate set; 0.0 if none
    recency: float                          # recency_weight(postmortem.occurred_at or created_at)
    overall_score: float                    # mean of the five subscores above
    rank: int                               # 1-indexed by overall_score, descending

class Citation(BaseModel):
    chunk_id: uuid.UUID
    postmortem_id: uuid.UUID
    quote: str | None = None

class Hypothesis(BaseModel):
    statement: str
    confidence: float
    citations: list[Citation] = Field(min_length=1)

class RunbookStepDraft(BaseModel):
    step: str
    source_postmortem_id: uuid.UUID | None = None
    citation: Citation | None = None

class DraftBrief(BaseModel):
    hypotheses: list[Hypothesis]
    runbook_steps: list[RunbookStepDraft]
    citations: list[Citation]               # flattened union of every hypothesis's citations

class VerificationResult(BaseModel):
    score: float
    is_grounded: bool
    issues: list[str]
    suggested_refinements: list[str]
    invalid_citations: list[Citation]       # dropped by the deterministic check -- for transparency

class IncidentBrief(BaseModel):
    incident_id: uuid.UUID
    version: int
    hypotheses: list[Hypothesis]
    matched_postmortems: list[CandidateMatch]
    blast_radius: BlastRadius
    runbook_steps: list[RunbookStepDraft]
    citations: list[Citation]
    overall_confidence: float | None        # mean hypothesis confidence, None if no hypotheses
    correction_passes: int
    llm_used: bool
    from_cache: bool
```

## `app/agents/nodes.py`

Each node is `async def node(state: TriageState) -> dict[str, object]` (LangGraph's
partial-update convention — a node returns only the keys it changes, not the whole
state) and takes `db: AsyncSession`, `graph_store: GraphStore`, `router: LLMRouter` via
`functools.partial` at graph-build time (`build_graph.py`), not as direct TypedDict
fields — dependencies aren't state.

1. **`normalizer_node`** — `router.structured(raw_text, system=..., result_type=
   IncidentSignalOut)`. Resolves `candidate_service_names` against
   `catalog_service.list_services(db, workspace_id)` (case-sensitive exact match on
   `Service.name`, mirroring Phase 6's real `service_linker_agent`/`extraction_service.py`
   resolution — `service_id_by_name.get(link.service_name)` — exactly, not an idealized
   case-insensitive version of it) — matched names become `affected_service_ids`, unmatched
   ones go to
   `unresolved_mentions`, never invented into a fake id). Persists an `IncidentSignal`
   row (`symptoms` JSONB stores `{"items": [...], "severity_guess": ...,
   "unresolved_mentions": [...]}` since the DB column has no dedicated columns for the
   latter two — `error_strings`/`metrics`/`affected_service_ids`/`time_window`/
   `extracted_by_model`/`extraction_confidence` map straight across). On
   `LLMUnavailableError`: sets `llm_used=False`, produces an empty `NormalizedSignal`
   (no symptoms, no resolved services) — the graph still proceeds; `retriever_node`'s
   query falls back to `raw_text` itself in that case (see below).

2. **`retriever_node`** — builds a query string: `" ".join(signal.symptoms +
   signal.error_strings)` if the signal has content, else `raw_text` verbatim (the
   no-LLM fallback above). On a retry (`retry_count > 0`), the query becomes `" ".join(
   [original_query, *verification.suggested_refinements])`, and any postmortem id in
   `verification.invalid_citations` is excluded from the result client-side after
   calling `hybrid_search` (not by extending Phase 7's `hybrid_search` signature —
   filtering the already-returned list keeps Phase 7's reviewed, tested contract
   untouched). Calls `hybrid_search(db, graph_store, workspace_id=..., query=...,
   mode="hybrid", top_k=settings.retrieval_top_k)` — this is the sole place this phase
   depends on Phase 7. Increments `retry_count` (FR-06 requires this happen here, not on
   the edge).

3. **`correlator_node`** — **no LLM.** `graph_store.blast_radius(workspace_id,
   signal.affected_service_ids)` → `state["blast_radius"]`. For every
   `SearchResultOut` in `retrieval.results`, builds a `CandidateMatch`: `vector_score`/
   `keyword_score`/`graph_score` read straight off that result's `sources` list
   (normalized per the field docstrings above; `0.0` for a source that didn't
   contribute); `failure_mode_overlap` from one batched query over
   `postmortem_failure_modes` for every candidate's `postmortem_id` (frequency-based
   recurrence scoring, see Gap #3 above); `recency` via the promoted
   `recency_weight(postmortem.occurred_at or postmortem.created_at)`. `overall_score`
   is the mean of the five; `rank` is 1-indexed by `overall_score` descending. Fully
   deterministic, fully unit-testable with a hand-built `retrieval` fixture and no
   network/model access at all.

4. **`analyst_node`** — prompt: `UNTRUSTED_DATA_NOTICE` (reused verbatim from Phase 6's
   `app/services/extraction/prompting.py`) + the normalized signal + the top-N
   `CandidateMatch`es with their subscores + each matched result's `chunk_excerpt`
   (already fenced per-chunk, same `<chunk id="...">` delimiting Phase 6 established).
   Wrapped by `app/services/llm/cache.py`: `get_cached(db, workspace_id=workspace_id,
   purpose="analyst_brief", prompt=prompt)` first; on a hit, `DraftBrief.model_validate
   (cached)` and `state["from_cache"] = True`, no LLM call at all. On a miss,
   `router.structured(prompt, system=..., result_type=DraftBrief)`, then `cache.store
   (...)` the result for next time. On `LLMUnavailableError` (neither cached nor live
   available): `llm_used=False`, `draft=DraftBrief(hypotheses=[], runbook_steps=[],
   citations=[])` — an explicitly empty draft, not a crash; `critic_node` and
   `route_after_critic` both special-case `llm_used=False` to skip straight through
   (Gap #2's whole reason for existing).

5. **`critic_node`** — **deterministic stage always runs, unconditionally:** the valid
   chunk-id set is `{r.chunk_excerpt.chunk_id for r in retrieval.results if
   r.chunk_excerpt}` — deliberately *not* every chunk that postmortem happens to own,
   only the ones actually shown to the analyst in its prompt, since citing an unseen
   chunk is exactly as ungrounded as citing a nonexistent one. A citation fails if its
   `chunk_id` isn't in that set, **or** if none of the hypothesis statement's
   length-≥4 word tokens (case-insensitive) appear in that chunk's `content` — a
   deliberately crude plausibility filter, not semantic entailment; it exists to catch
   obviously-wrong citations cheaply, not to replace the LLM judge below. Every failing
   citation is dropped from `draft.citations`/its hypothesis and recorded in
   `invalid_citations`; a hypothesis left with zero citations after dropping is itself
   dropped (FR-05's "hard fail regardless of what an LLM thinks"). **LLM stage,
   skipped entirely when `llm_used=False`:** on whatever draft content survives the
   deterministic pass, `router.structured(..., result_type=VerificationResult)` judges
   groundedness/completeness/`suggested_refinements`; when skipped,
   `VerificationResult(score=1.0, is_grounded=True, issues=["no LLM available -- brief
   is deterministic-only"], suggested_refinements=[], invalid_citations=[...])` — a
   score that always routes to `briefer_node`, never a retry, since retrying gains
   nothing without an LLM.

6. **`briefer_node`** — assembles `IncidentBrief` from `draft`, `candidates`,
   `blast_radius`, `verification.score` (→ `overall_confidence` as the mean hypothesis
   confidence, or `None` if `hypotheses` is empty), `retry_count` (→
   `correction_passes`), `llm_used`, `from_cache`. Persists a new `Brief` row:
   `version = 1 + (max existing version for this incident_id, or 0)`, `status =
   BriefStatus.READY`, JSONB columns from the corresponding `IncidentBrief` fields
   (`.model_dump(mode="json")`), `generated_at = now()`.

## `app/agents/edges.py`

```python
def route_after_critic(state: TriageState) -> Literal["retriever", "briefer"]:
    if not state["llm_used"]:
        return "briefer"                        # Gap #2 -- nothing to gain from retrying
    verification = state["verification"]
    settings = get_settings()
    if (
        verification.score < settings.critic_threshold
        and state["retry_count"] < settings.max_correction_passes
    ):
        return "retriever"
    return "briefer"
```

Pure function of `state` plus `Settings` — no I/O, exhaustively unit-testable against a
truth table (see NFR Testability).

## `app/agents/build_graph.py`

```python
def build_graph(db, graph_store, router) -> CompiledStateGraph:
    graph = StateGraph(TriageState)
    graph.add_node("normalizer", partial(normalizer_node, db=db, router=router))
    graph.add_node("retriever", partial(retriever_node, db=db, graph_store=graph_store))
    graph.add_node("correlator", partial(correlator_node, db=db, graph_store=graph_store))
    graph.add_node("analyst", partial(analyst_node, db=db, router=router))
    graph.add_node("critic", partial(critic_node, router=router))
    graph.add_node("briefer", partial(briefer_node, db=db))
    graph.add_edge(START, "normalizer")
    graph.add_edge("normalizer", "retriever")
    graph.add_edge("retriever", "correlator")
    graph.add_edge("correlator", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges("critic", route_after_critic, {"retriever": "retriever", "briefer": "briefer"})
    graph.add_edge("briefer", END)
    return graph
```

`checkpointer_conn_string(settings) -> str` converts `Settings.database_url`
(`postgresql+asyncpg://...`, SQLAlchemy's driver-qualified form) to the plain
`postgresql://...` DSN `AsyncPostgresSaver.from_conn_string` requires (confirmed live
against this project's real dev Postgres this phase — see the ADR) — a one-line
`str.replace`, not a new settings field, since it's a mechanical format conversion of an
existing value, not new configuration. `config={"configurable": {"thread_id":
str(incident_id)}}` is passed at invocation time so the checkpointer keys state by
incident, not globally.

**Not wired into `app/main.py`'s lifespan this phase, deliberately.** `AsyncPostgresSaver
.from_conn_string` is an async context manager — holding one open for the app's entire
lifetime with no current caller (Phase 9's incidents API doesn't exist yet) would add a
second Postgres connection pool and a `setup()` round-trip to every test that boots the
app via the ASGI test client, for zero benefit today — the same restraint this codebase
already applied to the LLM router (lazy provider construction) and the semantic cache
(built in Phase 6, wired to its real caller only once one existed, per ADR 0006 §2).
Phase 8's own verification (`build_graph`/`checkpointer_conn_string` used directly
inside a script/test fixture) needs no app-level wiring at all; compiling the graph once
at FastAPI startup happens in Phase 9, whose incidents API is this graph's first real
caller.

## `app/agents/streaming.py`

```python
async def stream_graph_events(
    graph: CompiledStateGraph, state: TriageState, *, thread_id: str, run_id: uuid.UUID
) -> AsyncIterator[dict[str, object]]:
```

No `db` parameter, deliberately — `astream_events` runs the graph as its own concurrent
task while this generator's body consumes events, so an `AgentRunStep` write sharing a
session with whatever the graph's nodes are bound to raced against the nodes' own
queries (`This session is provisioning a new connection; concurrent operations are not
permitted`), the same class of bug ADR 0007 §1 documents for Phase 7's concurrent
retrievers — caught only by actually running a real graph through the real streaming
wrapper, not by reasoning about the design. Each `AgentRunStep` write opens its own
fresh session via `get_session_factory()` instead.

Wraps `graph.astream_events(state, config={"configurable": {"thread_id": thread_id}},
version="v2")`, filtering to `on_chain_start`/`on_chain_end` events whose `name` matches
a node name (LangGraph emits many internal events per step; only node-level ones matter
here). For each node's `on_chain_start`, yields `{"type": "node_start", "node": name}`;
on `on_chain_end`, computes elapsed ms since the matching start, writes an
`AgentRunStep` row (`run_id`, `seq` incrementing, `node_name`, `status`, `latency_ms`,
`input_summary`/`output_summary` as small JSON-safe dicts — never the full state, which
can contain full chunk text), and yields `{"type": "node_end", "node": name,
"latency_ms": ...}`. Emits `{"type": "retry"}` when `route_after_critic` sends control
back to `retriever` (detected by seeing `"retriever"` start a second time within one
run). Emits a final `{"type": "done", "brief_id": ...}` or `{"type": "error", "message":
...}` depending on how the stream ends. This phase implements and unit-tests the
generator itself (against a graph run with a mocked LLM); wiring it into a real SSE HTTP
response is Phase 9's job.

## Data Model Changes

None — every table this phase writes to (`incident_signals`, `briefs`,
`agent_run_steps`) already exists from Phase 1. This phase is the first to actually
write to any of them.

## Dependencies

Phase 4's `GraphStore.blast_radius`, Phase 6's `LLMRouter`/`LLMUnavailableError`/
`UNTRUSTED_DATA_NOTICE`/`cache.py`, Phase 7's `hybrid_search`/`SearchResponseOut`. Phase
9's `incidents_service` and SSE endpoint are this phase's sole downstream consumer.
