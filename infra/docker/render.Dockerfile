# Single-process image for Render's free web service (512 MB). See scripts/allinone.py.
# Postgres and Redis are Render's managed free Postgres and Key Value (DATABASE_URL / REDIS_URL).
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FASTEMBED_CACHE_PATH=/app/.cache/fastembed EMB_CACHE_DIR=/app/.cache \
    WEB_DIST=/app/apps/web/dist MCP_ALLOWED_HOSTS=* GIGSIM_ERROR_RATE=0.02 MALLOC_ARENA_MAX=2
RUN pip install uv==0.9.5
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/req.txt && uv pip install --system -r /tmp/req.txt
COPY . .
COPY --from=web /web/dist apps/web/dist
# Pre-download the open embedding/reranker models and pre-embed the persona corpora so a 0.1-vCPU instance
# does not spend its first minutes embedding.
RUN LLM_OFFLINE=1 python -m scripts.warm_cache
CMD ["python", "-m", "scripts.allinone"]
