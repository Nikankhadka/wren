# T-035: production image for the ECS Fargate task (architecture.md section 9).
# Multi-stage: uv resolves/builds the venv in one layer, the runtime layer only
# ships the venv + app source, keeping the final image lean.
#
# The image is LEAN by construction: sentence-transformers/torch (the local
# EMBEDDER/RERANKER dev default, ~100MB+ - too heavy for the 0.25vCPU/0.5GB
# Fargate task) lives in pyproject's `local-ml` dependency group, installed by
# default everywhere EXCEPT here (--no-group local-ml below). The ECS task
# definition therefore binds EMBEDDER/RERANKER to hosted providers
# (infra/ecs.tf) - launching this image with EMBEDDER=local or RERANKER=local
# fails at first use with ModuleNotFoundError, by design.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --no-group local-ml

COPY . .
RUN uv sync --frozen --no-dev --no-group local-ml

FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 wren
WORKDIR /app

COPY --from=builder --chown=wren:wren /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER wren

EXPOSE 8000

# ECS Fargate ignores container HEALTHCHECK - the task definition's own ALB
# target-group health check (T-035) is authoritative in production. Kept here
# anyway since it's what `docker run`/local compose actually honor.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
