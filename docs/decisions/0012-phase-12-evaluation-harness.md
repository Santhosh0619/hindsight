# ADR 0012: Evaluation Harness — An Honest Tied Ablation, and Two Interaction Bugs Only a Real Browser Caught

## 1. Ablation modes compose Phase 7's retrieval primitives directly, not a new `SearchMode`

**Context.** The live search API's `SearchMode` (`hybrid`/`vector`/`keyword`/`graph`,
Phase 7) has no `vector_bm25` option — the ablation table needs exactly that middle
configuration (vector + keyword, no graph) alongside plain `vector` and the existing
`full` (=hybrid).

**Decision.** `runner.py`'s own `_retrieve_ranked_ids` composes `search_vector`/
`search_keyword`/`search_graph`/`reciprocal_rank_fusion` directly, selecting the
retriever subset by ablation mode, rather than adding a fourth value to `hybrid_search`'s
`SearchMode` literal. `hybrid.py`'s two dedup helpers
(`best_hit_per_postmortem`/`ranked_ids`) were promoted from module-private to exported
so both call sites share the exact same tie-breaking logic instead of two copies
drifting apart. This keeps the live search API's contract untouched — a finished,
reviewed module from three phases ago — and keeps the eval harness's own composition
logic in one small function that's actually about evaluation, not a special case
threaded through `hybrid_search`'s four-mode branch structure.

## 2. Citation validity is deterministic, using facts the corpus already has — no LLM call

**Context.** Master-Prompt.md's own phrasing calls citation validity "deterministic,"
distinct from groundedness's "LLM judge." Checking it for real means having a draft
brief with citations to check in the first place, and this build has no LLM key
configured (a standing choice since Phase 6).

**Decision.** `_stub_draft_brief` derives a minimal `DraftBrief` from the top-retrieved
postmortem's own `PostmortemFact` rows (root_cause → hypothesis, remediation →
runbook step, both cited to their real `source_chunk_id`) — the identical shape
`app/seed/seed.py`'s `_precompute_brief` already established for the same reason in
Phase 11. `metrics.citation_validity` then runs that draft through Phase 8's existing
`app.agents.citation_check.validate_citations` unmodified. No LLM call anywhere in this
path; `groundedness` is the only metric gated on `llm_configured`, and correctly
degrades to `None` (never `0%`) without a key — verified live via the CLI and the F11
page against the real seeded corpus.

## 3. The three ablation modes tied exactly on the real corpus — reported honestly, not forced apart

**Context.** plan.md §13 explicitly asks for an honest ablation table, including "if
graph retrieval doesn't improve recall, report that honestly." Running
`make eval MODE=all` against the real 20-case golden set produced identical numbers for
`vector`, `vector_bm25`, and `full` (recall@1=0.70, recall@5=0.95, mrr≈0.808) — every
column, to three decimal places.

**Decision.** Verified this wasn't a bug in the composition logic before accepting it:
directly ran `search_keyword`/`search_graph` against all 20 real eval-case queries and
got 0/20 hits for both, across the whole corpus. The root cause is the eval-case fixture
text itself (Phase 11's `generate_incidents.py`/`generate_eval_cases.py`) — short,
vague alert phrasing that deliberately never literally names a service (the precondition
`search_graph`'s substring match needs) and deliberately uses different vocabulary from
postmortem prose (the precondition BM25's `@@` match needs, and the same property Phase
11's own ADR 0011 already documented producing `keyword_score=0.0` for precomputed
briefs). On this particular corpus, vector search alone already saturates at
recall@5=0.95, so neither component gets a chance to show lift. This is a real,
measured, non-cherry-picked result — the PRD's acceptance criteria were corrected to
stop asserting the opposite once the numbers came back, rather than reshaping the test
to force a more flattering table. It's also a legitimate answer to plan.md §17 Q5 ("what
did graph retrieval actually add, and why") that says something concrete about *this*
corpus rather than making a generic claim about hybrid retrieval in the abstract.

## 4. A click handler that worked in a unit test but not in a real browser

**Context.** `EvalTrendChart`'s first version wired a click handler onto each `Line`'s
static `dot` render only. `AblationTable.test.tsx`/`EvalTrendChart.test.tsx` both passed,
`tsc`/`eslint`/`build` were clean, and the frontend code-reviewer's first pass flagged
the *absence* of any click wiring at all (FRD said "click a past run in the trend chart
or a mode in the ablation table" as two equivalent paths; only the table had one).

**Decision.** Added a custom `dot` render, then discovered — only by testing the fix
live in a browser — that recharts renders a *separate* `activeDot` element on top of the
static dot during hover, and that's the element actually under the cursor for a click at
the exact moment a user (or Playwright) clicks a point. Wiring the click handler onto
`dot` alone meant the click always landed on an invisible default `activeDot` overlay
first, going nowhere. Fixed by passing the same `ClickableDot` to both `dot` and
`activeDot` on both `Line`s. Confirmed correct by dispatching a raw DOM click event and
watching a genuinely different `EvalRun` id get fetched (visible in the network log and
in the drill-down's numbers changing) — Playwright's own synthetic `.click()` sequence
didn't reliably land on the hover-repositioned SVG element in a headless run, but a
single real click does, which is what actually matters. No unit test in this codebase
exercises recharts' internal dot/activeDot layering; this is a case where the live
walkthrough (this project's established practice since Phase 3) caught something
`vitest`+`jsdom` structurally cannot, since `fireEvent.click` on a manually-queried
element bypasses real hit-testing and z-order entirely.

## 5. A partial fallback bug, and the test that was worded to miss it

**Context.** `AblationTable`'s FRD requirement is "a mode with no run yet renders 'not
yet run' instead of blank cells." The first implementation applied that fallback to the
recall@1 column only; recall@5 and MRR silently fell back to an empty string. The
component's own test asserted `getAllByText("not yet run")` had length 2 — which is
true for a *correct* implementation (2 missing modes) and was also true for this *buggy*
one, since it only produces one occurrence per missing mode instead of three.

**Decision.** Fixed the component to apply the same fallback to all three columns, and
rewrote the test's assertion to `toHaveCount(6)` — 2 missing modes × 3 columns — with a
comment stating explicitly why 2 wouldn't have caught the original bug. The
`e2e/tests/evaluation.spec.ts` test had copied the same wrong expectation
(`toHaveCount(2)`) before the fix; updated in lockstep once the component fix landed.
Caught by the code-reviewer sub-agent reading the FRD's literal wording against the
code, not by any tool — the general lesson, consistent with this project's own pattern
across earlier phases (e.g. ADR 0007 §4's engineered-collision rewrite), is that a
passing count-based assertion can be numerically compatible with more than one
implementation, including the wrong one, unless the count is derived from the actual
requirement rather than picked to match whatever the first draft happened to produce.

## 6. `docker-compose.test.yml`'s services need an explicit rebuild that the dev stack doesn't

**Context.** `e2e/tests/evaluation.spec.ts` needs at least one real `EvalRun` seeded
into the isolated test database. `api-test` already runs `app.seed.seed` once at
startup; extending that startup command to also run `evaluation.cli --mode vector`
seemed sufficient — but the first `docker compose -f docker-compose.test.yml up -d
--wait` after that change produced `"evaluation CLI not present yet (Phase 12) --
skipping eval step"` in the logs, and the e2e test correctly failed against an empty
state.

**Decision.** Unlike the main `docker-compose.yml`'s `api`/`worker`/`web` services,
`docker-compose.test.yml`'s `api-test`/`worker-test`/`web-test` don't bind-mount source
— their code is `COPY`'d into the image at build time, so an image built before this
phase's backend code existed has no `app/services/evaluation/` at all, regardless of
what the current git working tree contains. Fixed by explicitly rebuilding
(`docker compose -f docker-compose.test.yml build api-test worker-test web-test`)
before bringing the stack up, not just `up -d --wait` on its own. Same underlying class
of gotcha as ADR 0010 §5 (a new frontend dependency not reaching the host because of
which paths are bind-mounted) and ADR 0011's need for a stale-image rebuild before
`app.seed` could be exercised — a recurring shape of bug in this project specifically
because the dev and test compose files intentionally use different source-delivery
mechanisms (bind mount for fast dev iteration, baked image for a test stack that's
supposed to represent what actually ships).
