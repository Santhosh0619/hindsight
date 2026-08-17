# Hindsight

> Your team has already solved this incident. Hindsight finds it.

Hindsight is a multi-tenant incident intelligence platform. It ingests a company's
postmortem archive and service catalog, then when a new incident opens, retrieves the
closest matching past incidents — with ranked root-cause hypotheses, source citations,
blast radius across the dependency graph, and a runbook drawn from what actually
worked last time.

**Status:** feature-complete, pre-deploy. Live demo link goes here once Phase 18 ships
it.

## The problem

Every engineering org accumulates postmortems, and after a few years nobody reads
them. When an alert fires at 2am, the fix is usually already written down somewhere —
a near-identical failure from fourteen months ago, with the root cause and the working
remediation both on record. Nobody finds it in time, for three reasons that compound:
the old postmortem uses different words than the new alert ("DB connection
saturation" vs. "504s on checkout"), the actual link between the two incidents is a
service-dependency relationship that exists nowhere in either document's text, and the
one engineer who'd remember the connection off the top of their head left the company
last year. Commercial incident tools (incident.io, Rootly, FireHydrant) help you *run*
an incident once it's open — none of them do retrospective correlation across a
dependency graph to help you find out you've already been here before.

## What it does

- **Generates a cited brief in seconds, not a search box.** File an incident and watch
  a six-node agent pipeline run live over SSE — normalize the alert, retrieve
  candidate postmortems three different ways, correlate them against the service
  graph, draft ranked hypotheses, and self-verify every citation before it ships. No
  claim in a brief lacks a citation to a real chunk of a real postmortem.
- **Shows blast radius, not just a match.** A recursive CTE over the service
  dependency graph tells you what's downstream of the affected service, weighted by
  edge criticality — before it becomes five separate incidents instead of one.
- **Explains why each result showed up.** Search results carry per-source attribution
  chips (vector, keyword, graph) so "why did this postmortem match" has a real answer,
  not a black-box similarity score.

## Evaluation

Measured against a 20-case evaluation set on the seeded demo corpus, comparing three
retrieval configurations:

| Configuration | recall@5 | MRR |
|---|---|---|
| Vector only | 0.950 | 0.808 |
| Vector + BM25 | 0.950 | 0.808 |
| Vector + BM25 + Graph (full) | 0.950 | 0.808 |

recall@1 is 0.700 across all three, and citation validity — the fraction of cited
claims that actually check out against the chunk they cite — is 1.0. The honest part
of this table is that all three configurations tie. On this corpus, at this size,
vector search alone already recovers the right postmortem in 19 of 20 cases within
the top 5, so BM25 and graph retrieval don't get a chance to show separation — recall
is already near its ceiling before they'd matter. That's a real finding about this
particular eval set's difficulty, not a bug in the harness, and it's reported as-is
rather than tuned until the numbers look more differentiated than they are. The
harness itself (recall@k, MRR, groundedness, citation validity) is a from-scratch
implementation, not a wrapper around an existing eval library — see
`docs/decisions/0012-phase-12-evaluation-harness.md` for the honest-ablation design
reasoning and `docs/decisions/0015-phase-15-tests.md` for how the test suite verifies
it stays deterministic.

## Architecture

```
React + TypeScript + Vite  ──REST + SSE──▶  FastAPI (async)
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                            ▼
                          DB-backed job queue          LangGraph agent pipeline
                          (ingest·embed·extract)        (see below)
                                    │                            │
                                    └──────────────┬─────────────┘
                                                    ▼
                              PostgreSQL 16 + pgvector — relational,
                              vector, and graph (recursive CTEs), one database
```

One Postgres database plays all three roles — relational, vector (`pgvector`), and
graph (recursive CTEs) — instead of the more common Postgres + a vector store + Neo4j
split. The short version: this service graph is small enough (hundreds of nodes, low
thousands of edges) that a recursive CTE outperforms a dedicated graph database on
both latency and operational cost, and a postmortem's text, embeddings, and
service-links commit in one transaction instead of three. Full reasoning, including
the actual scale at which that trade would flip, is in `docs/architecture.md`.

## The agent pipeline

Six LangGraph nodes, with a self-correcting loop:

```
normalizer → retriever → correlator → analyst → critic ──▶ briefer
                 ▲                                 │
                 └── score below threshold, retries remain ──┘
```

The retriever fuses three retrieval methods with Reciprocal Rank Fusion (vector,
keyword/BM25, and graph expansion over the service dependency graph). The critic
checks every citation deterministically — token overlap between the claim and the
cited chunk, not "ask the LLM if it's right" — and sends the draft back to the
retriever with a refined query if the verification score comes in low, up to a fixed
retry budget. Full pipeline detail, including the prompt-injection guardrail for
postmortem text, is in `docs/architecture.md`.

## Tech stack — free tier only, no card required

| Layer | Choice |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2 |
| Agents | LangGraph + LangChain + pydantic-ai |
| LLM | Gemini (free, no card) → Groq (free fallback) → Ollama (fully local) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2`, 384-dim, CPU — **no API key at all** |
| Database | PostgreSQL 16 + pgvector |
| Keyword search | Postgres `tsvector` + `rank_bm25` reranking |
| Graph | Postgres recursive CTEs behind a swappable `GraphStore` protocol |
| Queue | DB-backed jobs table with lease + backoff — no Redis, no broker |
| Auth | argon2id password hashing, JWT access + httpOnly refresh cookies |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui, React Query |
| CI | GitHub Actions — lint, type-check, tests, migration check, e2e |

Every layer here runs on a free tier or entirely locally. The one piece that needs no
key under any configuration is embeddings, which is why search and retrieval work
even in a build with zero LLM keys configured.

## Quick start

```bash
git clone <this-repo>
cd hindsight
cp .env.example .env
make dev      # starts Postgres + API + worker + frontend via Docker Compose
make seed     # loads the demo corpus: 80 postmortems, 40 services, 12 incidents
```

Open `http://localhost:5173` and click "Try live demo" for an instant, no-signup
walkthrough of a populated workspace. `.env` works unmodified with no LLM key set —
retrieval and search run entirely on local embeddings; add a free Gemini or Groq key
(see the comments in `.env.example`) to enable brief generation, or run Ollama
locally for a fully offline setup.

## Limitations — the honest version

- **The evaluation set is synthetic and was authored by the same person who built the
  retriever.** That's a real, acknowledged bias — a genuinely independent eval set
  would be more convincing, and isn't what this project has.
- **The failure-mode taxonomy is a fixed list.** A postmortem describing a failure
  mode outside that list gets force-fit into the closest category rather than
  recognized as novel.
- **Service-to-postmortem linking is heuristic**, not guaranteed-correct — it infers
  which services a postmortem concerns from its text and structure, which can misfire
  on ambiguous writing.
- **Retrieval quality is bounded by postmortem quality.** A vague or badly-written
  postmortem retrieves poorly no matter how good the retrieval pipeline is underneath
  it — garbage in, garbage matched.

## Project structure

```
backend/    FastAPI application, LangGraph agents, retrieval, evaluation harness
frontend/   React + TypeScript web app
e2e/        Playwright end-to-end tests, run against the full Docker stack
docs/       Architecture, data model, one ADR per phase, module PRD/FRD/NFR docs
```

## Roadmap

Sixteen phases shipped: foundation, auth, the frontend shell, the service catalog,
ingestion, extraction agents, hybrid retrieval, the LangGraph pipeline, the incidents
API, the service map/dashboard, seed data and demo mode, the evaluation harness,
observability/settings/API keys, a hardening pass, a test-coverage pass, and CI/
container work. What's left is Phase 18: deploying to a live URL and running the full
verification checklist against production — the DB on Neon, the backend on Fly.io or
HF Spaces, the frontend on Vercel, confirmed working with the LLM key removed.

## License

MIT — see `LICENSE`.
