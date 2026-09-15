FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN uv venv && uv pip install .

# --- runtime stage ---
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    GROUPOFFICE_READONLY=true

ENTRYPOINT ["groupoffice-mcp-server"]
