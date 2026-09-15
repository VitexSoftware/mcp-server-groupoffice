FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.14 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN uv venv && uv pip install .

# --- runtime stage ---
FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79

RUN groupadd --gid 1000 groupoffice \
    && useradd --uid 1000 --gid groupoffice --no-create-home --shell /usr/sbin/nologin groupoffice

WORKDIR /app
COPY --from=builder --chown=groupoffice:groupoffice /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    GROUPOFFICE_READONLY=true

USER groupoffice

ENTRYPOINT ["groupoffice-mcp-server"]
