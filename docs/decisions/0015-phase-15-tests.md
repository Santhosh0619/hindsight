# ADR 0015: Tests — A Wider Network Leak Than Planned, and a Tautological Meta-Test

## 1. The "no test touches the network" fix landed at `conftest.py`, not one test file

**Context.** The FRD's first draft scoped the network-touch violation to a single
test, `test_settings_api.py::test_llm_test_reports_unconfigured_slots_without_calling_them`,
with a planned fix of a file-local `monkeypatch` on `llm_test_service.OllamaLLMProvider`.
Running the new `test_api_smoke.py` sweep for the first time (before that fix landed)
took ~280 seconds instead of the few seconds every other generated sweep in this
project has taken, and traced back to real TCP connection attempts against
`ollama_base_url`. `OllamaLLMProvider` needs no API key, so it's *always* constructed
regardless of which providers are actually configured — reachable from two real
production call paths, not one: `llm_test_service.test_all_providers` (the
`/settings/llm/test` route) and `build_router()`, called for real inside the actual
`POST .../incidents/{id}/brief` route handler. Any test exercising either path — which
turned out to include the new smoke sweep itself — was opening a real socket.

**Decision.** Replaced the planned per-file mock with a single `autouse` fixture in
`conftest.py`, `_prevent_real_ollama_network_calls`, that monkeypatches
`OllamaLLMProvider`'s three `LLMProvider` protocol methods (`complete`/`structured`/
`structured_with_usage`) at the *class* level. This closes every current and future
call path through the provider by construction, rather than requiring each test file
that happens to exercise a brief-generation or LLM-test route to remember its own
mock — the same "fix it once, at the source" reasoning as ADR 0014 §2's
`max_request_bytes` correction, just discovered by running the new test rather than by
writing the FRD's numbers down first. `test_settings_api.py`'s own test needed no
local mock at all once this landed.

## 2. A `KNOWN_UNCOVERED` meta-test that could never fail

**Context.** Both generated sweeps (`test_rbac.py`, `test_api_smoke.py`) shipped a
meta-test intended to catch a new route landing with neither generated coverage nor a
documented `KNOWN_UNCOVERED` reason:
```python
found = set(_all_routes())
accounted_for = found | set(KNOWN_UNCOVERED)
missing = found - accounted_for
assert missing == set()
```
The single combined code-review pass (Step 9) caught that this is a tautology:
`found - (found | X)` is the empty set for *any* `X`, including an empty dict or one
full of nonsense entries. The assertion could never fail, regardless of what happened
to the route table — it provided zero protection against the exact scenario the FRD
claimed it guarded.

**Decision.** Replaced it with a test that checks the *other* direction —
`set(KNOWN_UNCOVERED) - found == set()` — which does have real failure modes: a
`KNOWN_UNCOVERED` entry left behind after its route is renamed or removed now fails
loudly instead of silently pointing at nothing. The direction the original test
attempted (a new route with no coverage and no exclusion) turns out to need no runtime
check at all: the parametrized case list is itself built as `found - KNOWN_UNCOVERED`,
so a route missing from both is structurally impossible by construction, not something
an assertion could ever catch. Also fixed a smaller, related FRD-accuracy gap the same
review pass flagged: `test_rbac.py` sent `json={}` unconditionally, including for
`DELETE`; now gated the same way `test_api_smoke.py` already gated its own body-bearing
methods. Same lesson as ADR 0014 §3: a generated/mechanical test's own generator logic
needs the same "does this assertion have a real failure mode" scrutiny as the routes
it's sweeping, and a single combined review pass catching it before merge is exactly
what Step 9 is for.
