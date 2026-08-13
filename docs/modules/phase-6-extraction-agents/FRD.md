# FRD: Extraction Agents (Pydantic AI)

## API Endpoints (Backend — FastAPI)

None. This phase has no HTTP surface — extraction runs entirely as a background job
triggered by ingestion. A later phase (Phase 9's incident API, or a knowledge-base
browse view) may expose `postmortem_facts`/`postmortem_services`/
`postmortem_failure_modes` read endpoints; not this phase's concern.

## React Components (Frontend)

None — backend-only phase per Master-Prompt.md's phase breakdown.

## Data Model Changes

None — `postmortem_facts`, `postmortem_services`, `postmortem_failure_modes`,
`failure_modes`, and `semantic_cache` already exist from Phase 1's initial migration
(verified against `backend/app/models/{postmortem,system}.py`). This phase adds no new
tables or columns.

## Internal Architecture

### `app/services/llm/provider.py` — the `LLMProvider` Protocol

```python
class LLMResponse(BaseModel):
    text: str
    tokens_in: int
    tokens_out: int
    model: str

class LLMProvider(Protocol):
    model_name: str
    async def complete(self, prompt: str, *, system: str) -> LLMResponse: ...
    async def structured(self, prompt: str, *, system: str, result_type: type[T]) -> T: ...
```

Verified against the installed `pydantic-ai` 2.29.0 (not the version Phase 0 originally
checked, 2.27.1 — re-verified since a minor bump can still move things): `Agent(model,
output_type=T, system_prompt=system)`, `await agent.run(prompt)` →
`AgentRunResult[T]`, typed value on `.output`, usage on `.usage` (a `RunUsage`
dataclass with `input_tokens`/`output_tokens`/`requests` — a property, not a callable,
which differs from an earlier assumption during this phase's own verification pass).

### `app/services/llm/{gemini,groq,ollama}.py` — concrete providers

Each wraps a pydantic-ai `Model` + `Provider` pair, constructed lazily (never at
import time, so a missing key/package never crashes module import — only an actual
call):

- `gemini.py`: `GoogleModel(model_name, provider=GoogleProvider(api_key=...))`
- `groq.py`: `GroqModel(model_name, provider=GroqProvider(api_key=...))` — requires
  the `groq` package, added as an explicit dependency this phase (pydantic-ai's
  Google support ships bundled by default; Groq does not — confirmed by import error
  against the actually-installed package, not assumed).
- `ollama.py`: `OllamaModel(model_name, provider=OllamaProvider(base_url=...))` — no
  API key; `base_url` from `Settings.ollama_base_url`.

Each provider's `complete`/`structured` builds a fresh `pydantic_ai.Agent` per call
(agents are cheap to construct; a provider instance is not a long-lived agent).

### `app/services/llm/router.py`

```python
class LLMRouter:
    def __init__(self, providers: list[LLMProvider]) -> None: ...
    async def complete(self, prompt: str, *, system: str) -> LLMResponse: ...
    async def structured(self, prompt: str, *, system: str, result_type: type[T]) -> T: ...
```

For each call, tries providers in the order given. Within a single provider, retries
up to 2 additional times via `tenacity.AsyncRetrying` on transient errors (timeouts,
5xx-shaped exceptions), with exponential backoff. If a provider exhausts its retries,
the router moves to the next provider. If every provider fails, raises
`LLMUnavailableError` (`app/core/errors.py`) with a message summarizing what was
tried — callers handle this by degrading, never by crashing.

`build_router(settings: Settings) -> LLMRouter` constructs the provider list from
`Settings`: `GeminiProvider` only if `llm_api_key` is set, `GroqProvider` only if
`groq_api_key` is set, `OllamaProvider` always included last (no key required). In this
build's actual configuration (no Gemini/Groq key, no local Ollama server running), the
provider list is just `[Ollama]`, and its connection failure against an unreachable
`localhost:11434` is what the router's normal "every provider failed" path turns into
`LLMUnavailableError` — matching FR-09's "fails cleanly" requirement without a separate
"zero providers configured" code path. `OllamaLLMProvider` is never omitted from the
list even with no other providers configured, since it's plan.md §10's documented
zero-key local fallback, not an optional extra.

### `app/services/llm/cache.py`

```python
async def get_cached(
    db: AsyncSession, *, workspace_id: UUID, purpose: str, prompt: str, threshold: float = 0.05,
) -> dict[str, object] | None: ...

async def store(
    db: AsyncSession, *, workspace_id: UUID, purpose: str, prompt: str, model: str,
    response: dict[str, object],
) -> None: ...
```

`get_cached` checks an exact SHA-256 hash of `prompt` first (cheap, no embedding call
needed); on a miss, embeds `prompt` (reusing Phase 5's `app.services.ingestion.embed`)
and searches `semantic_cache` for the closest embedding within the same
`workspace_id`+`purpose` via pgvector cosine distance, returning a hit if the distance
is below `threshold`. A hit increments `hits` in place. Not wired into the extraction
agents this phase — see PRD Out of Scope.

### `app/services/extraction/taxonomy.py`

```python
class FailureModeFamily(enum.StrEnum):
    CONFIGURATION_ERROR = "configuration_error"
    DEPLOYMENT_FAILURE = "deployment_failure"
    CAPACITY_EXHAUSTION = "capacity_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    NETWORK_CONNECTIVITY = "network_connectivity"
    DATA_CORRUPTION = "data_corruption"
    CODE_DEFECT = "code_defect"
    HUMAN_PROCESS_ERROR = "human_process_error"
    SECURITY_INCIDENT = "security_incident"
    INFRASTRUCTURE_HARDWARE = "infrastructure_hardware"
    SCALING_LOAD = "scaling_load"
    MONITORING_GAP = "monitoring_gap"
    OTHER = "other"
```

12 families + `other`, defined here (not in plan.md/Master-Prompt.md, which only say
"12 recurring failure-mode families" without naming them) — see the ADR for the
rationale behind this specific list.

### `app/services/extraction/facts_agent.py`

```python
class FactItem(BaseModel):
    statement: str
    chunk_id: uuid.UUID
    confidence: float | None = None

class ExtractedFacts(BaseModel):
    triggers: list[FactItem]
    root_causes: list[FactItem]
    remediations: list[FactItem]
    detection_gaps: list[FactItem]
    contributing_factors: list[FactItem]

async def extract_facts(
    router: LLMRouter, *, chunks: list[PostmortemChunkOut]
) -> ExtractedFacts: ...
```

Prompt lists each chunk with its `chunk_id` and content, explicitly delimited and
labeled as untrusted data (FR-08), and instructs the model to cite only the
`chunk_id`s given. `extraction_service.py` (not this module) is what actually drops
any returned fact whose `chunk_id` isn't in the real set — the agent module itself
just calls the LLM and returns its typed (unvalidated-against-the-DB) output; the
hallucination guard is deliberately a separate, deterministic step so it's testable
independently of any particular model's behavior.

### `app/services/extraction/failure_mode_agent.py`

```python
class FailureModeClassification(BaseModel):
    family: FailureModeFamily
    confidence: float

class FailureModeClassificationResult(BaseModel):
    classifications: list[FailureModeClassification]

async def classify_failure_modes(
    router: LLMRouter, *, chunks: list[PostmortemChunkOut]
) -> FailureModeClassificationResult: ...
```

### `app/services/extraction/service_linker_agent.py`

```python
class ServiceLink(BaseModel):
    service_name: str
    role: ServiceLinkRole
    confidence: float | None = None

class ServiceLinkResult(BaseModel):
    links: list[ServiceLink]

async def link_services(
    router: LLMRouter, *, chunks: list[PostmortemChunkOut], known_service_names: list[str]
) -> ServiceLinkResult: ...
```

Prompt includes the workspace's actual service names as a reference list (not
guaranteed the model only returns from that list — that guarantee is
`extraction_service.py`'s job, same separation-of-concerns as the facts agent above).

### `app/services/extraction_service.py`

Orchestrates all three agents for one postmortem and persists deterministic,
validated results:

- `run_extraction(db, router, *, postmortem_id) -> ExtractionSummary` — loads the
  postmortem's chunks, calls all three agents, then:
  - **Facts:** drops any `FactItem` whose `chunk_id` isn't among the loaded chunk
    ids; inserts one `PostmortemFact` row per surviving item.
  - **Failure modes:** for each classification, get-or-creates a `FailureMode` row
    scoped to the workspace (`label` = the family's value; the taxonomy is fixed in
    code, but its DB rows are workspace-scoped, matching the existing schema), then
    inserts a `PostmortemFailureMode` link row.
  - **Service links:** resolves each `service_name` against
    `catalog_service.list_services(db, workspace_id)` by exact name match (case-
    sensitive, matching Phase 4's `UniqueConstraint("workspace_id", "name")`); drops
    unresolved names; inserts one `PostmortemService` row per resolved link.

### `app/workers/handlers/extract_postmortem.py`

The `extract_postmortem` job handler: loads the postmortem, builds an `LLMRouter` via
`build_router(get_settings())`, calls `extraction_service.run_extraction`. On
`LLMUnavailableError` (or any other exception), re-raises so the worker's normal
`fail()`/backoff/dead-letter path handles it — no special-casing beyond what every
other job kind already gets (FR-09).

### `app/workers/handlers/ingest_postmortem.py` (modified)

After `index_postmortem` succeeds, enqueues one `extract_postmortem` job
(`payload={"postmortem_id": ...}`) — chains extraction automatically onto a
successful ingestion, per FR-07. A postmortem whose ingestion job fails never reaches
this point, so extraction is never attempted on unindexed content.

## Dependencies

Depends on Phase 1's `FailureMode`/`PostmortemFact`/`PostmortemService`/
`PostmortemFailureMode`/`SemanticCache` models (unchanged), Phase 4's
`catalog_service.list_services` (for service-name resolution), and Phase 5's
`ingest_postmortem` handler (which this phase modifies to chain extraction) and
`embed()` (reused by the cache module). Every later LLM-calling phase (Phase 8's
analyst node) depends on this phase's `LLMProvider`/`LLMRouter`.

## Sequence Flows

**Successful extraction**
1. `ingest_postmortem`'s handler reaches `status=indexed` and enqueues
   `extract_postmortem`.
2. The worker claims it, loads the postmortem's chunks, builds a router from
   `Settings`.
3. All three agents run against the router; each returns typed, unvalidated output.
4. `extraction_service` deterministically filters (hallucination guard, service-name
   resolution) and persists the surviving facts/classifications/links in one pass.

**No LLM configured**
1. `extract_postmortem`'s handler calls the router; the router's provider list is
   empty (or every configured provider fails).
2. `LLMUnavailableError` propagates out of the handler.
3. The worker's existing `fail()` path retries with backoff, then dead-letters after
   `max_attempts` — `jobs.last_error` reads something like "All LLM providers
   unavailable" the whole time, inspectable by a human without any extraction-specific
   tooling.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Model returns a fact citing a `chunk_id` not in the postmortem | Dropped before persisting — never reaches `postmortem_facts` |
| Model returns a service name not in the workspace's catalog | Dropped — never creates a new `Service` row, never links to the wrong one |
| Model returns zero classifications / facts / links | Persisted as zero rows — not an error, just an honest "extraction found nothing here" |
| No LLM provider configured | `LLMUnavailableError`, job retries then dead-letters, postmortem's own `status` (from ingestion) is unaffected |
| A configured provider is unreachable (network/quota) | `tenacity` retries within that provider, then the router falls through to the next configured provider |
| Postmortem deleted before its extraction job runs | Handler treats a missing postmortem as a no-op success, same pattern as Phase 5's `ingest_postmortem` |
| Postmortem's own ingestion failed (never reached `indexed`) | `extract_postmortem` is never enqueued — extraction only ever chains off a successful ingestion |
| Injection-flagged postmortem | Extraction proceeds normally; the prompt-level untrusted-data delimiting (FR-08) is what prevents the injected text from being followed, not a block on the postmortem itself |
