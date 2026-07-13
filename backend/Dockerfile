# T-035: production image for the ECS Fargate task (architecture.md section 9).
# Multi-stage: uv resolves/builds the venv in one layer, the runtime layer only
# ships the venv + app source, keeping the final image lean.
#
# NOTE (flagged, not resolved here): pyproject.toml's sentence-transformers dep
# (local embedder/reranker, T-009/T-016) pulls in torch - per .agents/memory.md
# T-016's entry this is documented as too heavy for the 0.25vCPU/0.5GB Fargate
# task the architecture doc specifies. Flip EMBEDDER/RERANKER to a hosted
# binding (azure/cohere) via task-def env vars before relying on this image in
# production, or split sentence-transformers into a dev-only dependency group -
# that split is real T-035 work, not done as a side effect of this Dockerfile.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

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
