## What this PR implements

<!-- Phase number and module name from plan.md. One paragraph. -->

## Reference

<!-- Phase N, modules B<X>/F<X> from plan.md §6 -->

## Checklist

### Workflow
- [ ] Feature branch created from main (Step 1)
- [ ] plan.md and Master-Prompt.md re-read (Step 2)
- [ ] Existing code explored (Step 3)
- [ ] PRD, FRD, NFR written and committed before any code (Step 4)

### Backend
- [ ] FastAPI code implements every FR-NN in PRD
- [ ] ruff: 0 errors
- [ ] mypy: 0 errors
- [ ] pytest: 0 failures
- [ ] code-reviewer sub-agent: APPROVED

### Frontend (React JS)
- [ ] React components implement every FR-NN in PRD
- [ ] tsc: 0 errors
- [ ] prettier: clean
- [ ] component tests: 0 failures
- [ ] build: succeeds
- [ ] code-reviewer sub-agent: APPROVED

### E2E
- [ ] Playwright tests cover all PRD acceptance criteria
- [ ] e2e-tester sub-agent: PASS (0 failures)

### Quality gates
- [ ] pre-push hook passed
- [ ] No AI attribution in any file, comment, commit, or string
- [ ] No secret or credential committed
- [ ] docs/decisions/ ADR written
- [ ] docs/design-notes.md updated

## Test results

<!-- Paste pytest summary: "N passed in Xs" -->
<!-- Paste playwright summary: "N passed" -->

## ADR summary

<!-- One sentence per architectural decision made in this phase. -->

## Screenshots (UI phases)

<!-- Before/after or new screens. One screenshot minimum for any phase with frontend work. -->
