FROM python:3.12-slim AS base
WORKDIR /app

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project
COPY src/ src/
COPY config/ config/
RUN mkdir -p data/threads data/documents logs

ENV PYTHONPATH=/app/src

# Non-root user
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app
USER botuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD .venv/bin/python -c "from proposal_assistant.health import check; check()" || exit 1

CMD [".venv/bin/python", "-m", "proposal_assistant.main"]
