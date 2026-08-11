# Skill: pr-workflow — Steps 13 and 14

## PR title format
```
<type>(phase-<N>): <imperative description, max 72 chars>
```
Examples:
- feat(phase-2): add auth with rotating refresh tokens
- feat(phase-8): implement LangGraph agent pipeline with corrective loop
- fix(phase-4): correct blast radius cycle detection

Title must not contain: Claude, AI, generated, assistant, automated.

## Create PR (Step 13)
```bash
gh pr create \
  --title "<type>(phase-N): <description>" \
  --body "$(cat .claude/pr-template.md)" \
  --base main \
  --head $(git branch --show-current)
```
Fill every section of the template. Delete nothing. Fabricate nothing.

## Merge criteria — every item must be true
- [ ] CI: all jobs green (author-check, backend, frontend, migration, e2e)
- [ ] code-reviewer sub-agent: APPROVED for both backend and frontend
- [ ] e2e-tester sub-agent: PASS
- [ ] pre-push hook: passed
- [ ] PR template: fully filled

## Merge (Step 14)
```bash
gh pr merge <pr-number> --merge --delete-branch
git checkout main && git pull origin main
git log --format="%an <%ae>" -1   # confirm author is correct
```

## After merge
- Branch deleted locally and remotely
- main pulled and up to date
- Next phase starts from Step 1 with a new branch
