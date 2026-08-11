# Skill: code-reviewer — Steps 7 (backend) and 10 (frontend)

## Invocation
Say: "Spawning code-reviewer sub-agent for <backend|frontend>, module: <name>"
Then apply this skill as the reviewer persona.

## What to read first
1. docs/modules/<name>/PRD.md
2. docs/modules/<name>/FRD.md
3. docs/modules/<name>/NFR.md
4. All new/changed files on the current branch (git diff main...HEAD)

## Backend review checklist

### PRD
- [ ] Every FR-NN is implemented and externally observable
- [ ] Out-of-scope items are absent from the code

### FRD — Endpoints
- [ ] Method + path match the FRD exactly
- [ ] Request Pydantic model matches
- [ ] Response Pydantic model matches
- [ ] Auth enforced by a FastAPI dependency (not just a comment)
- [ ] Error status codes match the FRD

### FRD — Data model
- [ ] Alembic migration exists and is correct
- [ ] All FRD indexes are present
- [ ] workspace_id filter on every tenant-scoped query
- [ ] workspace_id enforcement is in the repository layer, not just the endpoint

### NFR
- [ ] No blocking call in an async handler
- [ ] No bare dict at any module boundary
- [ ] Full type hints on every function
- [ ] structlog used (not print/logging.info)
- [ ] Typed exceptions from app/core/errors.py
- [ ] No hardcoded secrets, keys, or model IDs

### Architecture (CLAUDE.md)
- [ ] No AI attribution in any file, comment, string, or docstring
- [ ] LLM not called in a request handler
- [ ] Pydantic v2 models at all boundaries

### Safety
- [ ] No secret in any string literal
- [ ] User-supplied input validated by Pydantic before use
- [ ] File/path inputs sanitized

## Frontend review checklist

### PRD
- [ ] Every FR-NN visible in the UI and testable by a user
- [ ] Out-of-scope features absent

### FRD — Components
- [ ] Component names and file paths match the FRD
- [ ] Props interfaces match
- [ ] API calls match the documented endpoints
- [ ] States managed match

### NFR
- [ ] TypeScript strict — no `any` without a comment
- [ ] API calls go through the typed API client (not raw fetch)
- [ ] Auth state handled by the auth context (not ad-hoc checks)
- [ ] Loading, error, and empty states all handled
- [ ] No hardcoded API URLs (must use env variable)

### Architecture
- [ ] No AI attribution anywhere
- [ ] React Query used for server state (not useState + useEffect for API calls)
- [ ] No secret or key in frontend code

## Output format
```
## Code Review: <Module Name> — <backend|frontend>
Branch: <name>

### Verdict: APPROVED | CHANGES REQUIRED

### Findings
[If none]: No findings. All requirements satisfied.

[If any]:
FINDING-001
File: <path>, line <N>
Category: PRD | FRD | NFR | Architecture | Safety
Severity: BLOCKING | WARNING | NOTE
Requirement: <which FR-NN or NFR item>
Found: <what the code does>
Expected: <what the doc says>
Fix: <specific change needed>

### Summary
Blocking: N | Warnings: N | Notes: N

### Next step
APPROVED → proceed to next step
CHANGES REQUIRED → fix all BLOCKING findings, re-run review from Step 7 or Step 10
```
