# Skill: branch-workflow

## Branch naming
```
<type>/phase-<N>-<short-slug>
```
Examples: feat/phase-1-foundation, feat/phase-4-catalog-graph, fix/phase-8-retry-loop

## Create (Step 1)
```bash
git checkout main && git pull origin main
git checkout -b <branch-name>
git branch --show-current   # must show new branch
```

## Merge (Step 14)
Prerequisites: CI green, code-reviewer APPROVED, e2e 100% pass.
```bash
gh pr merge <pr-number> --merge --delete-branch
git checkout main && git pull origin main
git log --oneline -3   # confirm merge commit shows correct author
```
Use --merge (not --squash) to keep the step history visible in git log.

## Never
- Commit directly to main
- Merge with failing tests or a BLOCKING review finding
- Delete a branch before its PR is merged
