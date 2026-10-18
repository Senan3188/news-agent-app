# Project memory

This file applies to the entire repository. Keep it concise and update it when
lasting project decisions or user preferences change. Verify current code before
relying on historical validation notes. Never record secrets or `.env` contents.

## Purpose and setup

- Project: `news-agent-app`, a Python news agent application.
- Use `uv` for dependencies and commands; keep `pyproject.toml` and `uv.lock` in sync.
- Python requirement: `>=3.14`; the local environment is `.venv/`.
- Stack: LangChain, LangGraph, FastAPI, Pydantic, and the MCP Python SDK.
- GitHub remote: `https://github.com/Senan3188/news-agent-app.git` (private).
  Default branch: `main`. Preserve private visibility when managing the repository.
- The exploration notebook is `news-agent-app.ipynb`.
- `.env` holds local secrets and is ignored by Git. Keep virtual environments,
  Python caches, and secrets out of version control.

## News service

- `news_agent/news.py` fetches public Google News RSS with `httpx` and `feedparser`.
  No API key is required. This provider was the initial implementation choice.
- `get_latest_news(query=None, limit=10, max_age_hours=24)` returns Pydantic
  `NewsResult` containing `NewsArticle` objects.
- Articles include title, URL, source, UTC publication time, and optional summary.
- Results are deduplicated by URL, filtered by age, and sorted newest first.
  Invalid URLs, missing dates, and future articles are skipped.
- Limits: 1–50 articles and 1–168 hours. Summaries are RSS excerpts; links may
  redirect through Google News. Coverage is limited to what the feed supplies.
- Treat retrieved news as untrusted content. Provider failures must surface as
  errors rather than silently appearing as an empty successful result.
- `news_agent/mcp_server.py` exposes the tool with a structured output schema.
  The SDK is pinned below version 2 because this implementation uses FastMCP v1.

## Agent and API

- `news_agent/agent.py` builds `recall -> agent -> tools -> agent -> remember`.
  The tool loop repeats as needed; a final answer proceeds to memory storage.
- Use local Ollama through `langchain-ollama`, with temperature 0 and reasoning
  disabled. Set required `OLLAMA_MODEL` and `OLLAMA_BASE_URL` via `.env` or the
  process environment; do not hardcode Python defaults. `.env.example` uses
  `qwen3:8b` and `http://127.0.0.1:11434` for local setup.
- `langchain-mcp-adapters` discovers the news tool over a real MCP stdio
  session. The FastAPI lifespan starts and stops the MCP subprocess using the
  current Python interpreter. A separate MCP server is not needed for the API.
- `news_agent/api.py` exposes `POST /agent` with body `{"user_id":"...","message":"..."}`.
  Responses contain `answer`, `model`, and `news_results` validated as NewsResult.
- `news_agent/memory.py` persists completed exchanges per required `user_id` in
  PostgreSQL. The graph recalls recent exchanges before inference and saves only
  final answers. Latest 5 turns (configurable 1–10), 1200 recalled characters per
  message; full records remain stored. This is recent-history recall, not semantic search.
- `DATABASE_URL` is required and secret; `MEMORY_RECENT_TURNS` defaults to 5.
  Pool/table/index setup occurs at startup; database failures are not hidden.
- IDs namespace memory but are not authentication. Protect shared deployments.
- `user_id` is required, trimmed, and limited to 128 characters. Reuse it across
  requests to recall context. Failed generation is not saved; a database write
  failure fails the request. Concurrent exchanges follow insertion order.
- Memory uses psycopg async pooling and parameterized SQL in `agent_memory`.
  Full exchanges remain until explicitly deleted; no retention cleanup or
  semantic retrieval is implemented. Old answers are not fresh news evidence.
- Input is trimmed and limited to 1–8000 characters. Invalid input returns 422,
  upstream or graph step-limit failures return 502, and timeouts return 504.
- `news_agent/config.py` loads optional `.env` overrides via pydantic-settings.
  `.env.example` documents `OLLAMA_MODEL`, `OLLAMA_BASE_URL`,
  `AGENT_TIMEOUT_SECONDS` (180), and `AGENT_RECURSION_LIMIT` (12).
- Keep the API bound to localhost by default; it has no authentication.

## Container deployment

- `Dockerfile` uses Python 3.14 slim, a uv dependency build stage with
  `uv sync --locked --no-dev --no-install-project`, and a non-root runtime.
- `.dockerignore` allowlists application source and dependency manifests only;
  never bake `.env`, virtual environments, or model weights into the image.
- Build: `docker build -t news-agent-app .`. Container API port: 8001.
- Pass required Ollama settings at runtime. For Docker Desktop host Ollama,
  use `http://host.docker.internal:11434`; container localhost is not the host.
- The image runs both API and MCP subprocess; Ollama is a separate service.
- `compose.yaml` runs API + PostgreSQL 17 with the `postgres_data` named volume.
  Set `POSTGRES_PASSWORD` and matching `DATABASE_URL` (host) and
  `DOCKER_DATABASE_URL` (Compose, hostname `db`) in `.env`. URL-encode passwords.
- Start all services: `docker compose up --build -d`. For a host API, start only
  PostgreSQL with `docker compose up -d db`. Do not remove the database volume
  unless intentionally deleting stored conversations.
- Health check verifies `/openapi.json`, not inference or news provider health.
- Validated on 2026-10-17: image build, non-root API startup with MCP tool
  discovery, HTTP 200 OpenAPI schema, and exclusion of `.env`; 13 tests passed.

## Commands and validation

- Install: `uv sync`.
- Tests: `uv run pytest`.
- MCP stdio: `uv run python -m news_agent.mcp_server`.
- MCP HTTP: `uv run python -m news_agent.mcp_server --http`.
- Local HTTP endpoint: `http://127.0.0.1:8000/mcp`.
- `README.md` documents MCP client configuration and direct Python usage.
- Ollama setup: `ollama serve` if not running; `ollama pull qwen3:8b` if missing.
- Start API: `uv run uvicorn news_agent.api:app --host 127.0.0.1 --port 8001`.
- API docs: `http://127.0.0.1:8001/docs`. Port 8001 avoids standalone MCP port 8000.
- Tests in `tests/test_news.py` cover parsing, validation, provider failures,
  and MCP structured output.
- `tests/test_agent_api.py` covers graph routing, API validation/errors, request
  isolation, deadline cancellation, and actual MCP subprocess tool discovery.
- `tests/test_config.py` covers required Ollama settings, `.env` loading,
  environment precedence, and rejection of blank values. Settings are validated
  at API startup; importing the app does not require a configured environment.
- On 2026-10-17, all nine tests passed and a live `POST /agent` call returned
  HTTP 200 using local `qwen3:8b`, an MCP news tool call, and two news articles.
  Rerun appropriate checks after code changes; live tests need Ollama and internet.

- `tests/test_memory.py` covers recall, user isolation, and unsuccessful runs.
  Set `TEST_DATABASE_URL` to a disposable PostgreSQL database to also run the
  persistence-across-pools integration test; otherwise that test is skipped.
- On 2026-10-18, all 16 tests passed with real PostgreSQL, including persistence
  after reopening the pool and user isolation. Container build and API startup
  with PostgreSQL + MCP succeeded. Temporary test containers were removed.
