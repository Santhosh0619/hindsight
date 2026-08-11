.PHONY: dev down migrate revision seed test test-be test-fe test-e2e lint typecheck \
        build logs shell-api shell-db hooks

# ── Dev environment ───────────────────────────────────────────────────────────
dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec db psql -U postgres hindsight

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

seed:
	docker compose exec api python -m app.seed.seed

# ── Testing ───────────────────────────────────────────────────────────────────
test: test-be test-fe test-e2e

test-be:
	docker compose exec api bash -c "ruff check . && mypy app --strict && pytest tests/ -v --tb=short -q"

test-fe:
	cd frontend && npx tsc --noEmit && npm run build && npm run test

test-e2e:
	docker compose -f docker-compose.test.yml up -d --wait
	cd e2e && npm run test
	docker compose -f docker-compose.test.yml down

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	cd backend && ruff check .
	cd frontend && npx eslint src/

typecheck:
	cd backend && mypy app --strict
	cd frontend && npx tsc --noEmit

# ── Hooks ─────────────────────────────────────────────────────────────────────
hooks:
	bash .claude/install-hooks.sh
