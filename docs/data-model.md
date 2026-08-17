# Data Model

Everything lives in one PostgreSQL 16 database with the `pgvector` extension —
relational tables, vector columns, full-text columns, and a graph expressed as
adjacency rows, all in the same schema with the same transactional guarantees. See
`docs/architecture.md` for why that's one database instead of three. This document
describes the schema as it actually exists today, read directly from
`backend/app/models/*.py` and the Alembic migrations, not from the earlier
planning sketch.

Every table below inherits an `id UUID PRIMARY KEY` (default `uuid4()`) unless noted
otherwise, and most inherit a `created_at TIMESTAMPTZ` set by the database's own
`now()` on insert. A handful of pure link/junction tables skip both and use a
composite primary key instead — called out per table.

## Identity & workspace

```
users(id, email UNIQUE, password_hash, full_name, is_active, is_demo, created_at)
refresh_tokens(id, user_id → users, token_hash UNIQUE, expires_at, revoked_at, user_agent, created_at)

workspaces(id, name, slug UNIQUE, is_demo, invite_code UNIQUE NULL, created_at)
workspace_members(workspace_id → workspaces, user_id → users, role ENUM[owner,responder,viewer], joined_at)
  PRIMARY KEY (workspace_id, user_id) — no separate id column, membership is the identity
audit_log(id, workspace_id → workspaces, actor_user_id → users NULL, action, target_type, target_id NULL, meta JSONB, created_at)
api_keys(id, workspace_id → workspaces, name, key_hash UNIQUE, prefix, created_by → users NULL, last_used_at NULL, revoked_at NULL, created_at)
```

`workspace_members` has no surrogate key — the `(workspace_id, user_id)` pair *is*
the row, which also means a user can't accidentally end up with two membership rows
in the same workspace; the database enforces that, not application code.
`workspaces.invite_code` is nullable and unique, so a workspace with invites disabled
just has `NULL` there rather than a separate flag.

## Catalog

```
teams(id, workspace_id → workspaces, name, slack_handle NULL, escalation_contact NULL, created_at)
services(id, workspace_id → workspaces, name, tier ENUM[1,2,3], team_id → teams NULL,
         repo_url NULL, description NULL, runbook_url NULL, created_at)
  UNIQUE (workspace_id, name)
service_edges(id, workspace_id → workspaces, from_service_id → services, to_service_id → services,
              kind ENUM[calls,reads_from,publishes_to,depends_on],
              criticality ENUM[hard,soft], created_at)
  UNIQUE (from_service_id, to_service_id, kind)
```

`service_edges` carries its own `workspace_id` even though it's derivable from either
endpoint's service row — a deliberate denormalization so every tenant-scoped query
(including the blast-radius CTE) filters on `workspace_id` directly, without a join,
matching the tenant-isolation rule described at the bottom of this document.

## Postmortems

```
postmortems(id, workspace_id → workspaces, external_ref NULL, title, occurred_at NULL,
            duration_minutes NULL, severity ENUM[sev1..sev4] NULL,
            raw_text, redacted_text NULL,
            status ENUM[pending,processing,indexed,failed], failure_reason NULL,
            injection_flagged, created_by → users NULL, created_at)

postmortem_chunks(id, postmortem_id → postmortems, chunk_index, section_label NULL,
                  content, char_start, char_end,
                  embedding VECTOR(384) NULL, tsv TSVECTOR NULL)
  — no created_at; chunks are immutable, generated once at ingest

failure_modes(id, workspace_id → workspaces, label, canonical_description NULL, category NULL)
  UNIQUE (workspace_id, label)

postmortem_facts(id, postmortem_id → postmortems,
                 fact_type ENUM[trigger,root_cause,remediation,detection_gap,contributing_factor],
                 statement, confidence NULL, source_chunk_id → postmortem_chunks,
                 extracted_by_model NULL)

postmortem_services(postmortem_id → postmortems, service_id → services,
                    role ENUM[root_cause,affected,downstream], confidence NULL)
  PRIMARY KEY (postmortem_id, service_id, role)

postmortem_failure_modes(postmortem_id → postmortems, failure_mode_id → failure_modes, confidence NULL)
  PRIMARY KEY (postmortem_id, failure_mode_id)
```

`postmortem_chunks.embedding` is a 384-dimension `pgvector` column — the dimension
matches `sentence-transformers/all-MiniLM-L6-v2`'s real output size, not a rounder
number picked for convenience. `raw_text` is what was uploaded; `redacted_text` is
what the redaction pass produced and what actually gets chunked/embedded/sent to an
LLM — the two are kept as separate columns rather than redacting in place, so the
original is still available for re-processing if the redaction rules change later.

## Incidents & briefs

```
incidents(id, workspace_id → workspaces, external_ref NULL, title, raw_alert_text,
          severity NULL, status ENUM[open,mitigated,resolved,false_positive],
          opened_by → users NULL, opened_at, resolved_at NULL, created_at)

incident_signals(id, incident_id → incidents, symptoms JSONB, error_strings TEXT[],
                 metrics JSONB, affected_service_ids UUID[], time_window JSONB,
                 extracted_by_model NULL, extraction_confidence NULL)

briefs(id, incident_id → incidents, version, status ENUM[generating,ready,failed],
       hypotheses JSONB, matched_postmortems JSONB, blast_radius JSONB,
       runbook_steps JSONB, page_list JSONB, citations JSONB,
       overall_confidence NULL, correction_passes, llm_used, from_cache,
       generated_at NULL)

brief_feedback(id, brief_id → briefs, user_id → users NULL,
               verdict ENUM[helpful,partially,unhelpful],
               correct_postmortem_id → postmortems NULL, note NULL, created_at)
```

`briefs` has no `workspace_id` of its own — it's reached through `incident_id →
incidents.workspace_id`, one hop, rather than duplicated. `correction_passes` and
`llm_used`/`from_cache` on `briefs` are the persisted trace of the corrective-RAG
loop described in `docs/architecture.md`: how many times the critic sent a draft back
to the retriever, whether the model was reachable at all for this run, and whether
this response came from the semantic cache instead of a fresh generation.

## Agent runs

```
agent_runs(id, incident_id → incidents, brief_id → briefs NULL, graph_version,
           status, started_at, finished_at NULL,
           total_tokens_in, total_tokens_out, error NULL)

agent_run_steps(id, run_id → agent_runs, seq, node_name, status, latency_ms NULL,
                tokens_in, tokens_out, input_summary JSONB, output_summary JSONB, error NULL)
```

Neither table has `created_at` — `started_at`/`finished_at` and each step's own
`latency_ms` already carry the timing information that matters here, and a separate
insert timestamp would just be redundant. `agent_runs.brief_id` is a detail that
didn't exist in the original schema sketch: it's set once the briefer node actually
persists a `Brief` row, so the observability page (Phase 13) can resolve a run's
cache-hit status with a direct join instead of guessing which of an incident's
brief versions a given run produced from timestamps alone.

## Evaluation

```
eval_cases(id, workspace_id → workspaces, name, incident_text,
           expected_postmortem_ids UUID[], expected_service_ids UUID[], notes NULL)

eval_runs(id, workspace_id → workspaces, git_sha NULL, mode NULL, started_at, finished_at NULL,
          recall_at_1 NULL, recall_at_5 NULL, mrr NULL, groundedness NULL,
          citation_validity NULL, cases_run, notes NULL)

eval_case_results(id, eval_run_id → eval_runs, eval_case_id → eval_cases,
                  retrieved_ids UUID[], rank_of_first_hit NULL, groundedness NULL, passed)
```

`eval_runs.mode` is the other real addition since the original sketch: it's what
lets one run be tagged `vector`, `vector_bm25`, or `full`, which is what makes the
ablation table in the README possible — the original schema had no way to tell three
retrieval configurations' runs apart.

## Jobs & cache

```
jobs(id, workspace_id → workspaces, kind, payload JSONB,
     status ENUM[queued,running,done,failed,dead],
     attempts, max_attempts, run_after, locked_by NULL, locked_at NULL,
     last_error NULL, created_at)

semantic_cache(id, workspace_id → workspaces, purpose, prompt_hash,
               embedding VECTOR(384) NULL, response JSONB, model, hits, created_at)
```

There's no separate message broker — `jobs` is the entire queue. A worker claims a
row with `UPDATE ... WHERE status='queued' AND run_after <= now() ... SKIP LOCKED`,
which is also why the index below exists.

## The indexes that matter

Quoted from the actual model/migration definitions, not asserted from memory:

- **HNSW on `postmortem_chunks.embedding`**, cosine distance ops:
  ```
  CREATE INDEX ix_postmortem_chunks_embedding_hnsw ON postmortem_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
  ```
- **GIN on `postmortem_chunks.tsv`** for the keyword side of retrieval:
  ```
  CREATE INDEX ix_postmortem_chunks_tsv_gin ON postmortem_chunks USING gin (tsv);
  ```
- **Partial index on the queue's claim query**, so it stays cheap as `jobs` fills up
  with `done`/`dead` rows instead of scanning the whole table:
  ```
  CREATE INDEX ix_jobs_claim_queue ON jobs (status, run_after) WHERE status = 'queued';
  ```
- **Composite `(workspace_id, status)` indexes** on the two tables whose primary
  list views filter on both at once — `postmortems` (`ix_postmortems_workspace_status`)
  and `incidents` (`ix_incidents_workspace_status`).
- Every other tenant-scoped table gets a plain index on `workspace_id` alone (visible
  as `index=True` on that column in each model above) — the composite ones above are
  the exception, added because those two tables' actual list queries filter on status
  too, not a blanket policy applied everywhere.

## Tenant isolation

`workspace_id` sits on every table above except the ones reached through a single
FK hop from something that already has it (`briefs` via `incidents`,
`postmortem_chunks`/`postmortem_facts` via `postmortems`, `agent_run_steps` via
`agent_runs`). The rule is enforced in the repository layer — every query that
touches a tenant-scoped table filters on the caller's `workspace_id`, not on
trusting that the object's own ID is enough. That rule isn't just stated here; it's
mechanically checked by `backend/tests/test_tenant_isolation.py`, a generated test
that walks the app's actual route table and confirms a workspace can't read another
workspace's resource through any endpoint that returns one — added in Phase 14, not
something this document asserts on faith.
