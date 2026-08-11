# Skill: test-runner

## Backend test sequence (Step 6) — all must pass before proceeding

```bash
cd backend

# 1. Lint
ruff check .
# On failure: fix errors, re-run. Do not suppress.

# 2. Type check
mypy app --strict
# On failure: fix type errors. Do not add type: ignore without a comment explaining why.

# 3. Tests
pytest tests/ -v --tb=short -q
# On failure: fix the CODE, not the test.
# Exception: if the test expectation is provably wrong, explain why before changing it.

# 4. Coverage (informational — do not chase a number, do not fake coverage)
pytest tests/ --cov=app --cov-report=term-missing -q
```

Pass criteria: ruff 0 errors, mypy 0 errors, pytest 0 failed 0 errors.

## Frontend test sequence (Step 9) — all must pass before proceeding

```bash
cd frontend

# 1. Type check
npx tsc --noEmit

# 2. Lint + format check
npx eslint src/ --max-warnings 0
npx prettier --check "src/**/*.{ts,tsx,css}"

# 3. Component tests
npm run test -- --run

# 4. Build (catches bundler errors tsc misses)
npm run build
```

Pass criteria: tsc 0 errors, eslint 0 warnings, prettier clean, 0 test failures, build succeeds.

## If any step fails
1. Read the full error output completely.
2. Fix the code (not the test/check config).
3. Re-run from step 1 of the sequence.
4. Never push with any failure. Never skip.

## Passing summary to print
```
✓ ruff clean
✓ mypy clean
✓ pytest: N passed in Xs
✓ tsc clean
✓ eslint clean
✓ prettier clean
✓ vitest: N passed
✓ build clean
All checks passed. Ready to proceed to code review.
```
