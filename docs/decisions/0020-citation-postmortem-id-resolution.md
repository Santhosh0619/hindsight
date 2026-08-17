# ADR 0020: Every Hypothesis Was Silently Dropped — Trusting the Model for a Fact the Server Already Had

## Context

Preparing demo material with a real LLM key on for the first time surfaced something
the zero-key dev path could never have caught: every single live-generated brief
showed "No hypotheses were generated for this incident," even when the analyst step's
own trace showed `hypothesis_count: 1` or `2` and the critic's own trace showed
`score: 1.0` with `invalid_citation_count: 0`. The model was producing real,
well-grounded hypotheses; something between the critic and the rendered brief was
losing them, with nothing in the logs pointing at why.

Root cause, found by reading `analyst_agent.py`'s actual prompt-rendering code rather
than guessing: `_render_candidates` shows the model each retrieved chunk wrapped in
`<chunk id="{chunk_id}" postmortem="{title}">` — the chunk's real UUID, but the
postmortem's *title*, never its UUID. The `Citation` schema the model has to fill in,
however, requires both `chunk_id` and `postmortem_id`. The model was never shown the
postmortem's id at all, so it had no way to report it accurately — in practice it
defaulted to an all-zero placeholder UUID rather than fail schema validation. Two
places then trusted that unreliable value:

1. `_enrich_brief` (`incidents_service.py`) resolved each citation's display data by
   looking up `postmortem_by_id.get(citation.postmortem_id)` — a lookup against a
   UUID no real postmortem has, so every citation resolved to `None` and got filtered
   out. `_citation_out` returning `None` for a hypothesis's only citation meant the
   hypothesis itself never made it into the API response — invisible to the frontend,
   with the backend's own `hypotheses` JSONB column (checked directly) still holding
   the real content the whole time.
2. `retriever_node`'s corrective-retry path (`nodes.py`) builds its exclusion set as
   `{c.postmortem_id for c in verification.invalid_citations}` — the same untrusted
   field, meaning a correction pass's "exclude the postmortems whose citations failed"
   refinement was silently excluding nothing, on every retry, in every run.

## Decision

Stopped asking the model to be the source of truth for a fact the server already has.
`PostmortemChunk.postmortem_id` is a real foreign key — given a `chunk_id`, the server
can resolve the owning postmortem deterministically, with zero risk of the kind of
error a model reproducing a 36-character UUID it was never shown is prone to. Fixed at
both points that mattered:

- `_enrich_brief`'s `_citation_out` now resolves `postmortem_id` from the already-
  fetched `chunk.postmortem_id`, not from `citation.postmortem_id`. The `postmortem_id`
  lookup set feeding that query is built from resolved chunks plus matched candidates,
  not from citations at all.
- `validate_citations` (`citation_check.py`) now corrects every citation's
  `postmortem_id` from a `chunk_id → postmortem_id` map built off the retrieval
  results themselves (data the server already has, not model output) before it's used
  anywhere — both the citations that survive into the persisted brief and the ones
  collected into `invalid_citations` for the retry-exclusion set.

Added a regression test (`test_a_wrong_postmortem_id_from_the_model_does_not_drop_the_citation`)
that deliberately hands the fake model an all-zero `postmortem_id` — the same failure
mode observed against the real API — and asserts the hypothesis and runbook step both
survive with the correct id resolved. The existing citation-enrichment test always
supplied the *correct* `postmortem_id` in its fake model's citation, which is exactly
why it never caught this: it tested the happy path a real model never actually
produces.

This is the same lesson ADR 0019 drew from the same testing session, in a different
place: nothing in 18 phases of zero-key development could have caught either bug,
because both only manifest once a real model is actually generating real, imperfectly-
reproduced output — and a live key, actually turned on and actually watched, is what
found them both within the same afternoon.
