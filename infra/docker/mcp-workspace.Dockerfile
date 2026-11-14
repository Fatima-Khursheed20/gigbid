# GigBid service: mcp-workspace
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_SYSTEM_PYTHON=1 FASTEMBED_CACHE_PATH=/app/.cache/fastembed
RUN pip install uv==0.9.5
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-hashes -o /tmp/req.txt && uv pip install --system -r /tmp/req.txt
COPY common common
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY apps/api apps/api
COPY apps/__init__.py apps/__init__.py
COPY worker worker
COPY gigsim gigsim
COPY evals/__init__.py evals/__init__.py
COPY scripts scripts
COPY data/personas data/personas
COPY data/policy_pack data/policy_pack
EXPOSE 8103
CMD ["python", "-m", "uvicorn", "mcp_servers.workspace.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8103"]
