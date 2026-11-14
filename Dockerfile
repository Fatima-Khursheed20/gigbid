# Single-container image for the public deployment (Hugging Face Docker Space, port 7860).
# Runs GigSim, the three MCP servers, the API (serving the web build) and the Arq worker under
# scripts/run_stack.py; Postgres and Redis are managed services given via DATABASE_URL / REDIS_URL secrets.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860 HOME=/home/user FASTEMBED_CACHE_PATH=/home/user/app/.cache/fastembed     MCP_ALLOWED_HOSTS=* WEB_DIST=/home/user/app/apps/web/dist
RUN useradd -m -u 1000 user && pip install uv==0.9.5
WORKDIR /home/user/app
COPY --chown=user pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-hashes -o /tmp/req.txt && uv pip install --system -r /tmp/req.txt
COPY --chown=user . .
COPY --chown=user --from=web /web/dist apps/web/dist
USER user
RUN python -c "from rag.index.embeddings import get_embedder, get_reranker; get_embedder(); get_reranker()"
EXPOSE 7860
CMD ["python", "-m", "scripts.run_stack"]
