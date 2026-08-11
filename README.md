# Hindsight — Incident Intelligence Platform

> Your team has already solved this incident. Hindsight finds it.

A multi-tenant platform that ingests your service catalog and postmortem archive,
then uses a hybrid vector + keyword + graph retrieval pipeline to surface matching
past incidents when a new one opens — with ranked root-cause hypotheses, citations,
blast radius, and a runbook assembled from what actually worked.

**Status:** In development.

## Stack

- Backend: FastAPI, PostgreSQL + pgvector, LangGraph, Pydantic AI
- Frontend: React 18, TypeScript, Vite, Tailwind, shadcn/ui
- Retrieval: Hybrid RAG (vector + BM25 + GraphRAG), Corrective RAG loop
- Free tier only — works without any API key

## Quick start

```bash
cp .env.example .env
make dev      # starts Postgres + API + worker + frontend
make seed     # loads demo data
```

Open http://localhost:5173 — click "Try live demo" for instant access.
