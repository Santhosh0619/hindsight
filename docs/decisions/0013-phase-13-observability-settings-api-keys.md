# ADR 0013: Observability, Settings, API Keys — Additive Retrofits, a Real Step-Writing Gap, and One Workflow Change

## 1. Real per-node token usage is retrofitted onto Phase 6/8 via additive methods, not signature changes

**Context.** `LLMProvider.structured()` (Phase 6) and `judge_verification()` (Phase 8)
already compute `result.usage.input_tokens/output_tokens` internally but never return it
— exactly what FR-01 needs to show real per-step token counts on the Agent Runs page.
Both functions already have live callers: `judge_verification` specifically is called by
Phase 12's evaluation harness (`app/services/evaluation/runner.py`), which has no use
for per-node tracking and expects a bare `LLMVerificationJudgment` back.

**Decision.** Added `structured_with_usage()` as a new method on the `LLMProvider`
protocol, alongside the existing `structured()`, implemented identically across
`gemini.py`/`groq.py`/`ollama.py`. `extract_signal`/`draft_brief` switch to it in place
(neither has a caller outside the live pipeline). `critic_agent.py` instead gains a new
sibling function, `judge_verification_with_usage`, leaving `judge_verification` itself
completely untouched. The cost is a few lines of duplication between the two critic
functions; the alternative — changing `judge_verification`'s return shape — would have
meant either breaking Phase 12's already-reviewed evaluation harness or growing a
conditional `include_usage` flag into a function whose whole job is a single LLM call.
Confirmed safe by Phase 12's own test suite staying green with zero changes.

## 2. `agent_runs.brief_id` is a new additive column, needed to answer "was this run served from cache"

**Context.** FR-02/FR-03 need `AgentRunOut.from_cache` and `AgentRunStatsOut
.cache_hit_rate`, both of which require knowing which `Brief` row a given `AgentRun`
actually produced. No FK existed between them — an incident can accumulate several
`AgentRun`/`Brief` pairs across regenerations with no way to line up a specific pair.

**Decision.** Added `agent_runs.brief_id` (nullable, `ON DELETE SET NULL`), set once in
`_finish_agent_run` from the `brief_id` the graph's own `done` event already carries.
While wiring this up, found that `generate_brief`'s non-streaming path (`POST
.../incidents/{id}/brief`, as opposed to the SSE `/brief/stream` route) called
`graph.ainvoke` directly instead of going through `stream_graph_events` — meaning a
real, token-spending run generated through that endpoint never wrote a single
`AgentRunStep` row. This is a genuine pre-existing gap from Phase 8/9, not something
introduced this phase, and it directly contradicts this phase's own promise that every
real run gets real step data. Fixed by routing `generate_brief` through
`stream_graph_events` too, draining it for its `done`/`error` events instead of calling
`ainvoke` — both entry points into brief generation now write identical step data by
construction. Covered by a regression test
(`test_generating_a_brief_writes_a_real_step_waterfall`) rather than left as an
untested fix.

## 3. API keys are hashed with SHA-256, not argon2

**Context.** Every other secret in this codebase (`hash_password`) uses argon2id. API
keys need the same "never store the plaintext" property but sit on a different access
pattern: authenticated on every single ingest webhook call, potentially high frequency,
versus a login form's occasional password check.

**Decision.** `apikey_service._generate_key()` uses `secrets.token_urlsafe(32)` (256
bits of real entropy) plus `hashlib.sha256`, not argon2. Argon2's deliberate slowness
exists to raise the cost of offline brute-forcing a low-entropy human-chosen password —
a threat model that doesn't apply to a randomly generated 256-bit token, where brute
force is already computationally infeasible regardless of hash speed. Using argon2 here
would only add latency to a high-frequency lookup path for no offsetting security
benefit. This is a deliberate, documented departure from `hash_password`'s choice, not
an inconsistency — the two hash different threat models and the FRD/NFR both spell out
the reasoning so a future reviewer doesn't flag it as a regression.

## 4. Settings' role gating lives at two levels: the existing page gate, plus new panel-level gates

**Context.** The first FRD draft claimed "the whole Settings page is owner-only," which
turned out to be wrong once actually building against `AppShell`'s real Phase 3 gate
(`useRequireRole("owner", "responder")`) and the fact that `GET .../members` is a
genuine any-role read on the backend.

**Decision.** Left `AppShell`'s page-level gate untouched — a responder still reaches
`/settings`. Within the page, `ApiKeysPanel`/`LlmProviderPanel`/`DangerZonePanel` render
only for `role === "owner"` (every one of their backend endpoints is owner-only),
`MembersPanel` renders its read view for both roles but only shows write controls
(role dropdown, remove, rotate invite) to an owner. Caught and fixed as a documentation
inaccuracy before any code was reviewed — the FRD was corrected to describe the design
actually being built, not adjusted after the fact to match a bug. `e2e/tests
/rbac-shell.spec.ts` now asserts this two-level gate directly: a responder sees
`MembersPanel` but not the three owner-only panel headings; an owner sees all four.

## 5. `docker-compose.test.yml`'s baked images needed an explicit rebuild — again

**Context.** The first e2e run against this phase's new frontend pages failed all three
new specs with the app rendering `StubRoute`'s "Settings isn't built yet" placeholder
instead of the real page — despite `tsc`/`vitest`/`build` all passing moments earlier
against the same source tree.

**Decision.** Same root cause ADR 0010 §5, ADR 0011, and ADR 0012 §6 already
documented: `web-test`/`api-test`/`worker-test` `COPY` source into the image at build
time rather than bind-mounting it, so a stale image has no way to see new files
regardless of what's on disk. Fixed with `docker compose -f docker-compose.test.yml
down` then `up -d --build --wait` before running Playwright. This is now a confirmed
recurring gotcha specific to this project's dev/test compose split (fast bind-mount
iteration for `dev`, baked image for a test stack meant to represent what actually
ships) rather than a one-off — worth checking first, not last, the next time an e2e
spec fails against code that demonstrably works in isolation.

## 6. Code review is now one pass per phase, not one per layer

**Context.** CLAUDE.md's Module Workflow spawned a code-reviewer sub-agent twice per
phase — once after backend code (Step 7), once after frontend code (Step 10) — each a
separate, full-context sub-agent invocation. By the time either review runs, the layer
under review is already lint/type/test clean, so a second full review pass buys
relatively little additional signal for its token cost.

**Decision.** Santhosh flagged this mid-Phase-13 and asked for one combined review
going forward. CLAUDE.md's Module Workflow was updated in the same session: the old
Step 7/Step 10 split collapses into a single Step 9 REVIEW, run once after both
CODE-FE and TEST-FE are done, covering the whole diff. Phase 13 itself still ran the
old two-pass way (both backend and frontend review already in flight when the feedback
landed), so it's the last phase built under the previous process.
