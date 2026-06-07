.PHONY: install run test lint typecheck check migrate revision fmt

install:           ## sync deps (incl. dev) and provision Python 3.12
	uv sync

run:               ## run the API locally with reload
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -q

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

check: lint typecheck test  ## everything CI runs

migrate:           ## apply migrations to DATABASE_URL (defaults to local sqlite)
	uv run alembic upgrade head

revision:          ## autogenerate a migration: make revision m="message"
	uv run alembic revision --autogenerate -m "$(m)"
