FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies into the system Python
RUN uv pip install --system --no-cache -e ".[prod]" 2>/dev/null || \
    uv pip install --system --no-cache -e "."

# ---- runtime stage ----
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
