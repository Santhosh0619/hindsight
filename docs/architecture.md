# Architecture

This document is for anyone evaluating the engineering, not the pitch — it goes one
level deeper than the README on the two decisions worth defending: why there's one
database instead of three, and how the agent pipeline actually works.

## System overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  React + TypeScript + Vite + Tailwind                                 │
│  httpOnly cookie auth · SSE for live agent traces · React Query       │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ REST + SSE
┌───────────────────────────────▼──────────────────────────────────────┐
│  FastAPI (async)                                                      │
│  auth · workspaces · catalog · incidents · search · eval · settings   │
│                              │                                        │
│      ┌───────────────────────┴────────────────────────┐              │
│      ▼                                                 ▼              │
│  ┌──────────────────┐                    ┌──────────────────────┐    │
│  │ DB-backed job     │                    │  LangGraph pipeline  │    │
│  │ queue + worker    │                    │  (see below)         │    │
│  │ ingest·embed·      │                   └──────────┬───────────┘    │
│  │ extract·eval       │                              │                │
│  └────────┬───────────┘                              │                │
└───────────┼─────────────────────────────────────────┼─────────────────┘
            │                                          │
            ▼                                          ▼
┌────────────────────────────────────┐   ┌───────────────────────────┐
│  PostgreSQL + pgvector             │   │  LLM provider router      │
│  ─ relational: users, workspaces,  │   │  Gemini (default)         │
│    services, incidents, briefs     │   │  Groq (fallback)          │
│  ─ vector: chunk embeddings (384d) │   │  Ollama (fully local)     │
│  ─ graph: recursive CTE traversal  │   └───────────────────────────┘
│  ─ queue: jobs table with leases   │
│  ─ traces: agent_runs / steps      │   ┌───────────────────────────┐
└────────────────────────────────────┘   │ Local embeddings          │
                                          │ all-MiniLM-L6-v2 (384d)   │
                                          │ no API key required       │
                                          └───────────────────────────┘
```

Four containers in development (`docker-compose.yml`): `db` (Postgres+pgvector),
`api` (FastAPI), `worker` (the job queue's async worker loop), `web` (the Vite dev
server). No Redis, no message broker, no separate vector store — that's the whole
point of the next section.

## Why one database instead of three

The obvious portfolio-RAG stack is Postgres for relational data, a vector database for
embeddings, and a graph database for service dependencies. Hindsight uses Postgres for
all three roles instead, via `pgvector` for embeddings and recursive CTEs for graph
traversal, behind a `GraphStore` protocol that keeps the graph implementation
swappable.

The reasoning, in order of how much it actually matters:

1. **The graph is small and shallow.** A real organization's service dependency graph
   is hundreds of nodes and low thousands of edges, and blast-radius queries only
   need to walk a handful of hops. A recursive CTE over an indexed foreign key does
   that in single-digit milliseconds. A dedicated graph database earns its keep at
   millions of edges or when you need variable-length pattern matching that SQL can't
   express reasonably — this system is nowhere near that line, and pretending
   otherwise would be adding infrastructure to look impressive rather than to solve a
   real problem.
2. **Transactional consistency.** A postmortem, its chunks, their embeddings, and the
   service links extracted from it all need to land together or not at all. In one
   database that's a single transaction. Split across three stores, it's an eventual-
   consistency problem you now have to design around for no functional benefit.
3. **Free-tier reality.** Neo4j AuraDB's free tier auto-pauses after three days of
   inactivity, which is a genuine problem for a project that needs to survive as a
   live demo between recruiter visits. Postgres on Neon's free tier doesn't have that
   failure mode.
4. **One backup, one connection pool, one migration path.** Every operational concern
   — schema migrations, connection limits, backup/restore — exists exactly once
   instead of three times, in three different tools, with three different failure
   modes to reason about.

The honest version of this decision isn't "graph databases are unnecessary" — it's
"this graph is small enough that a dedicated graph database doesn't pay for itself
yet, and the `GraphStore` protocol means swapping in Neo4j later is a new
implementation of one interface, not a rewrite." The threshold where that trade flips
is somewhere around low millions of edges or a need for genuinely variable-length
pattern matching (find all services within *N* hops satisfying some structural
condition) that a recursive CTE stops expressing cleanly. Nothing about this system is
near that line today.

## The agent pipeline

An incoming incident goes through six LangGraph nodes, with one conditional loop back
into retrieval:

```
START → normalizer → retriever → correlator → analyst → critic ──┐
             ▲                                                    │
             │ score < threshold and retries remain                │
             └────────────────────────────────────────────────────┘
                                                    │ otherwise
                                                    ▼
                                                 briefer → END
```

1. **Normalizer** — a Pydantic-AI structured agent turns freeform alert text into a
   typed `IncidentSignal`: symptoms, error strings, candidate services, a time window.
2. **Retriever** — three retrieval methods run and get fused with Reciprocal Rank
   Fusion: vector search over chunk embeddings (semantic similarity), keyword search
   (Postgres `tsvector` plus BM25 reranking — needed because an error code like
   `ORA-12520` is a token match, not a concept a vector search reliably surfaces), and
   graph search over postmortems linked to the candidate services and their close
   neighborhood.
3. **Correlator** — pure graph logic, no LLM call: a recursive CTE computes blast
   radius downstream of the affected services, weighted by edge criticality and
   service tier, and scores candidate postmortems by failure-mode overlap and temporal
   proximity.
4. **Analyst** — the LLM synthesis step. It drafts hypotheses, runbook steps, and
   citations from the retrieved and correlated evidence. Every claim in the draft is
   required to carry a citation to a real chunk id, and the retrieved postmortem text
   is explicitly delimited in the prompt and marked as untrusted data — postmortems
   are user-uploaded text, and treating them as instructions rather than data is
   exactly the failure mode a prompt-injection defense has to close (more below).
5. **Critic** — self-verification, and this is where it gets interesting. Citation
   validity is checked deterministically first, not by asking the LLM to grade its own
   work: `citation_check.py` extracts the meaningful tokens (four characters or
   longer) from each claim and from the cited chunk's actual content, and a claim only
   passes if the two token sets overlap. That's a real, cheap, LLM-independent check
   that catches a citation pointing at a chunk id that exists but doesn't actually
   support the claim. On top of that, the critic scores overall groundedness and
   signal/hypothesis consistency and returns a `VerificationResult`.
6. **Briefer** — finalizes and persists the brief, versions it, and streams it to the
   frontend over SSE as each node completes, so a responder watches the trace happen
   live rather than waiting on a spinner.

**The corrective loop.** If the critic's score falls below `critic_threshold` (0.7 by
default) and the run hasn't exhausted `max_correction_passes` (2 by default), control
returns to the retriever with a refined query built from the critic's flagged issues,
instead of shipping a brief that failed its own verification. If the LLM was
unavailable for the whole run, the loop doesn't fire — there's nothing to gain from
retrying against a still-unavailable provider, so a degraded (retrieval-only, no
synthesis) result ships instead of looping forever.

**Why a state machine instead of a linear chain.** A linear pipeline can't express
"go back two steps and try again with new information" without becoming a state
machine in disguise, badly. LangGraph makes that loop the explicit, typed thing it
actually is, with the state itself — a Pydantic `TypedDict` — checkpointed to Postgres
after every node. That means a brief survives a worker restart mid-run, and every hop
between nodes is a real Pydantic model (`IncidentSignal`, `RetrievalResult`,
`CandidateMatch`, `DraftBrief`, `VerificationResult`), never a raw string passed
between steps and hoped to be shaped correctly.

## The prompt-injection guardrail

Postmortems are user-uploaded text that eventually gets fed to an LLM, which makes
them an injection surface most portfolio RAG projects don't have a story for at all.
Hindsight's defense is two layers, deliberately not one:

- **At ingest**, `screen()` flags (never blocks) postmortem text containing
  instruction-like phrases ("ignore previous instructions," "you are now," "new
  instructions:") or zero-width Unicode characters commonly used to hide injected
  text from a human reviewer. A flagged postmortem still gets indexed —
  `injection_flagged` is a signal, not a gate, because false positives on legitimate
  incident language ("ignore the alert noise from service X") are a real risk and a
  block would be the wrong failure mode.
- **In the analyst prompt**, retrieved postmortem content is explicitly delimited and
  the model is instructed to treat it strictly as data, never as instructions —
  because the ingest-time flag alone doesn't stop an unflagged, cleverly-worded
  injection attempt from reaching the LLM; the real defense is architectural (the
  model is told what it's looking at), and the flag is an audit signal on top of it.

## LLM routing and the zero-key path

The LLM router (`app/services/llm/router.py`) tries providers in a fixed order —
Gemini, then Groq, then Ollama — retrying twice per provider before moving to the
next, so a single exhausted quota or a transient timeout doesn't fail the whole run.
Ollama needs no API key at all, which is why the whole system — including the
`/settings/llm/test` connectivity check and every route that constructs an LLM
provider — is reachable with zero keys configured. `docs/decisions/0015-phase-15-tests.md`
covers the test suite's own network-isolation fix for exactly this provider, which
exists precisely because it's constructed unconditionally in real request paths.
Embeddings never touch
this router at all — `sentence-transformers/all-MiniLM-L6-v2` runs in-process on CPU,
so search works even in a build with no LLM key and no Ollama running locally.

## Further reading

- `docs/data-model.md` — the real schema, read from the SQLAlchemy models.
- `docs/decisions/` — one ADR per phase, the actual record of what went wrong and why
  a decision was made the way it was, not the retrospective clean version.
