.PHONY: dev down migrate revision seed test test-be test-fe test-e2e lint typecheck \
        build logs shell-api shell-db hooks eval

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

# ── Evaluation ────────────────────────────────────────────────────────────────
# MODE defaults to `all`, running the three-way ablation (vector / vector_bm25 / full)
# and printing the README-ready comparison table; pass MODE=vector|vector_bm25|full to
# run just one.
eval:
	docker compose exec api python -m app.services.evaluation.cli --mode $(or $(MODE),all)

# ── Testing ───────────────────────────────────────────────────────────────────
test: test-be test-fe test-e2e

test-be:
	docker compose exec api bash -c "ruff check . && mypy app --strict && pytest tests/ -v --tb=short -q --cov=app/services --cov=app/agents --cov-report=term-missing"

test-fe:
	cd frontend && npx tsc --noEmit && npm run build && npm run test

test-e2e:
	docker compose -f docker-compose.test.yml up -d --wait
	cd e2e && npm run test
	docker compose -f docker-compose.test.yml down

# ── Containers ────────────────────────────────────────────────────────────────
# Local-only verification that both production Dockerfile stages still build cleanly
# -- not used by CI (which doesn't build images at all yet; that's Phase 18's deploy
# step), just a way to catch a broken Dockerfile before an actual deploy attempt.
build:
	docker build --target production -t hindsight-backend:local ./backend
	docker build --target production -t hindsight-frontend:local ./frontend

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
