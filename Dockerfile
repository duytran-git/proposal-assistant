FROM python:3.12-slim AS base
WORKDIR /app

# Install Node.js 18+ (required by Claude Agent SDK CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen
COPY src/ src/
COPY config/ config/
RUN mkdir -p data/threads data/documents logs

# Non-root user
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app
USER botuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "from proposal_assistant.health import check; check()" || exit 1

CMD ["uv", "run", "python", "-m", "proposal_assistant.main"]
