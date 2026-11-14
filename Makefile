# GigBid — make dev | test | eval | seed | demo | lint
PY ?= uv run python

.PHONY: install dev test lint eval seed demo web gen-api compose e2e
install:
	uv sync --extra dev && cd apps/web && npm ci

seed:            ## regenerate synthetic personas, GigSim seed and labelled dev set
	$(PY) -m scripts.gen.run_all

dev:             ## run GigSim, MCP servers, API (serving the web build) and worker locally
	cd apps/web && npm run build
	$(PY) -m scripts.run_stack

web:
	cd apps/web && npm run dev

gen-api:         ## regenerate the typed TS client from FastAPI's OpenAPI schema
	cd apps/web && npm run gen:api

lint:
	uv run ruff check . && $(PY) -m scripts.ci_checks && cd apps/web && npx tsc -b

test:
	LLM_OFFLINE=1 uv run pytest -q -W ignore::UserWarning

e2e:
	cd apps/web && npx playwright test

eval:            ## retrieval metrics, decision metrics, fixed GigSim reply-rate run -> evals/results/*.json
	LLM_OFFLINE=1 $(PY) -m evals.runners.rag_eval --limit 60 --out rag_retrieval
	LLM_OFFLINE=1 $(PY) -m evals.runners.rag_eval --ablate v4_outcome --limit 60 --out rag_ablation
	$(PY) -m evals.runners.decision_eval --per-persona 25
	$(PY) -m evals.runners.gigsim_outcomes --variants v0_naive,v4_outcome --per-persona 5
	$(PY) -m evals.runners.agency_routing

demo:            ## end-to-end smoke through the HTTP API of a running stack
	$(PY) -m scripts.e2e_api --email $$REVIEWER_EMAIL --password $$REVIEWER_PASSWORD --approve

compose:
	docker compose -f infra/docker-compose.yml --env-file .env up --build
