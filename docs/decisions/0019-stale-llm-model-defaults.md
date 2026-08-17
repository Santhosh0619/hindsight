# ADR 0019: Stale LLM Model Defaults, Found by Actually Turning the Key On

## Context

The project ran for 18 phases with `LLM_API_KEY` unset in every dev/CI session — a
deliberate choice (works-without-a-key is a core requirement) that also meant nobody
had actually exercised a live LLM call against real free-tier accounts since whenever
`llm_model`/`groq_model`'s defaults were first chosen. Turning a real Gemini and Groq
key on for the first time (to prepare demo material) surfaced three real, previously
invisible problems in about ten minutes of testing:

1. **`gemini-2.5-flash`** (the original default) returns a 404 from Google's own API:
   "no longer available to new users." The model still exists and is even listed by
   the `/v1beta/models` endpoint — it's an account-tier restriction, not a removed
   model, which a naive "does the model exist" check wouldn't catch.
2. **`llama-3.3-70b-versatile`** (Groq's original default) is gone entirely. Querying
   Groq's real `/v1/models` endpoint with the actual key returned zero Llama models —
   their current lineup is `openai/gpt-oss-*`, `qwen/*`, and a couple of others.
3. **`.env.example` claimed leaving `LLM_MODEL` blank falls back to the code default.**
   It doesn't. `pydantic-settings` treats a present-but-empty env var as the literal
   value `""`, not as "unset" — so a blank `LLM_MODEL` passed `model=""` straight to
   the provider and failed every call with "model is required." This is the class of
   bug that's invisible until someone actually sets a key and watches it fail, which
   describes this exact project's testing history precisely.

## Decision

Fixed all three at the source, each verified against the real provider before being
written down — the same discipline this project has applied to every other "these
move fast, don't guess" caution since Phase 0:

- `llm_model` default → `gemini-flash-lite-latest`, chosen only after
  `gemini-flash-latest` (a plausible first choice, and Google's own recommended
  replacement in the 404 error body) returned a *persistent* 503 "high demand" across
  repeated attempts on this same free-tier key. `gemini-flash-lite-latest` completed
  both a plain and a structured call reliably in the same session — confirmed with
  real calls, not assumed correct because it's listed.
- `groq_model` default → `openai/gpt-oss-20b`, the fastest/cheapest model in Groq's
  current lineup with tool-calling and structured-output support, which this
  project's `structured()` calls need. (Its own free-tier TPM budget is tight enough
  that back-to-back calls in the same run can hit a rate limit — acceptable for a
  fallback provider that Gemini is expected to handle first.)
- `.env.example` no longer tells anyone a blank `LLM_MODEL`/`GROQ_MODEL` is safe — both
  are set to explicit, verified values, with a comment explaining why blank is actually
  unsafe rather than just asserting a value.

Also fixed a real, if minor, frontend bug found in the same session: `BriefView.tsx`
showed "this brief is deterministic-only" whenever `hypotheses` was empty, regardless
of whether the LLM actually ran — a live Gemini-generated brief (real runbook text,
real matched incidents, `llm_used: true`) still showed that message because the model
returned zero hypotheses for that specific alert. The existing test fixture had
encoded the same bug (`llm_used: true` fixture, asserting the "deterministic-only"
copy) without anyone noticing, because nothing before this session had generated a
live brief with an empty hypotheses list to catch the mismatch. Fixed to branch on
`llm_used`, with a second test covering the case the first test's fixture had
accidentally been hiding.

None of these three problems were reachable by the test suite, CI, or code review —
every one needed a real API key actually turned on and a real brief actually generated
to surface. That's the practical argument for doing this verification now, before
capturing demo material that depends on it looking right, rather than deferring it
further.
