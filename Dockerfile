FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="AI Inference Layer" \
    org.opencontainers.image.authors="Alisha Karma <lishykarma99@gmail.com>" \
    org.opencontainers.image.source="https://github.com/codealisha99/ai-inference-layer"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY ai-inference-server-py/pyproject.toml ai-inference-server-py/README.md ./
COPY ai-inference-server-py/src ./src
RUN pip install .

RUN useradd --create-home --uid 10001 app \
    && mkdir /data && chown app:app /data
USER app

# Railway injects DATABASE_URL for durable Neon PostgreSQL storage.
ENV PORT=3000
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=2)"

CMD ["ai-inference-server"]
