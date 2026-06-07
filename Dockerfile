# Reproducible production image. uv installs from the committed lockfile; Alembic
# migrations run on boot (see start.sh), then uvicorn serves the app.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /uvx /bin/

WORKDIR /app

# 1) Dependencies as their own cached layer (changes rarely).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2) Application code + install the project itself.
COPY . .
RUN uv sync --frozen --no-dev && chmod +x start.sh

CMD ["./start.sh"]
