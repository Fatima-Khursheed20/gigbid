# GigBid Portfolio MCP server

A read-only MCP server that turns **your own portfolio folder** (CV, case studies, repo READMEs and code, client
reviews, past proposals with outcomes) into evidence you can cite. It runs the same retrieval GigBid ships:
requirement decomposition, BM25 and dense fusion, open cross-encoder reranking, and multi-vector project items.
Everything runs locally on CPU with open models (fastembed/ONNX); no API key is needed.

## Install / run
```bash
# any MCP host, stdio transport (no install needed beyond uv)
PORTFOLIO_DIR=/path/to/my/portfolio uvx --from git+https://github.com/Fatima-Khursheed20/gigbid gigbid-portfolio-mcp

# or HTTP (streamable) on :8101
uvx --from git+https://github.com/Fatima-Khursheed20/gigbid gigbid-portfolio-mcp --http --port 8101
```

Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"portfolio": {"command": "uvx",
  "args": ["--from", "git+https://github.com/Fatima-Khursheed20/gigbid", "gigbid-portfolio-mcp"],
  "env": {"PORTFOLIO_DIR": "/Users/me/portfolio"}}}}
```
Cursor: the same command and env in `.cursor/mcp.json`.

## Folder layout
```
portfolio/
  profile.json              optional: name, headline, rates
  projects.json             optional: [{id, title, client, industry, date}]  (metadata for every chunk)
  cv.pdf | cv.md
  case_studies/<project-id>.md
  repos/<repo>/README.md + source files, optional .project_id
  reviews.jsonl             {"id","project_id","text","rating","date"}
  proposals.jsonl           {"id","text","outcome":"won|replied|ignored","cited_project_ids":[...]}
```
Files can be added at any time. The index rebuilds incrementally on the next query, and embeddings are cached.

## Tools (all `readOnlyHint=true`)
| Tool | What it does |
|---|---|
| `search_evidence(requirement, k, filters)` | ranked evidence items with type, source, date and outcome; filters: types, outcome, min_date, project_id |
| `requirement_matrix(requirements)` | each requirement → supporting evidence + status (supported / weak / none) via a corrective retrieve-grade-requery loop; `none` means *do not claim it* |
| `get_case_study(case_id)` | full case study with metadata |
| `list_skills()` | skills evidenced anywhere, including ones visible only in code imports |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://profile`.
Prompts: *Answer a screening question from my portfolio*, *Will I fit this job?*, *Turn a repo into a case study outline*.

## Try it with the bundled synthetic persona
```bash
PORTFOLIO_DIR=$(pwd)/data/personas/ai_ml uv run gigbid-portfolio-mcp     # from a clone of the repo
npx @modelcontextprotocol/inspector uv run gigbid-portfolio-mcp            # MCP Inspector
```
