FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

RUN useradd --create-home --uid 10001 app \
    && mkdir /data && chown app:app /data
USER app

# Models and inference history live in SQLite on a volume so they survive restarts.
# Unset DATABASE_PATH to run purely in memory instead.
ENV PORT=3000 \
    DATABASE_PATH=/data/ai-inference.db
VOLUME /data
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=2)"

CMD ["ai-inference-server"]
