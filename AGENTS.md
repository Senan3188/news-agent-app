# Project memory

This file applies to the entire repository. Keep it concise and update it when
lasting project decisions or user preferences change. Verify current code before
relying on historical validation notes. Never record secrets or `.env` contents.

## Purpose and setup

- Project: `news-agent-app`, a Python news agent application.
- Use `uv` for dependencies and commands; keep `pyproject.toml` and `uv.lock` in sync.
- Python requirement: `>=3.14`; the local environment is `.venv/`.
- Stack: LangChain, LangGraph, FastAPI, Pydantic, and the MCP Python SDK.
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

## Commands and validation

- Install: `uv sync`.
- Tests: `uv run pytest`.
- MCP stdio: `uv run python -m news_agent.mcp_server`.
- MCP HTTP: `uv run python -m news_agent.mcp_server --http`.
- Local HTTP endpoint: `http://127.0.0.1:8000/mcp`.
- `README.md` documents MCP client configuration and direct Python usage.
- Tests in `tests/test_news.py` cover parsing, validation, provider failures,
  and MCP structured output. Four tests and a live RSS request passed on
  2026-10-17; rerun appropriate checks after changes.
- LangChain/LangGraph agent orchestration and a FastAPI REST app have not yet
  been implemented. The MCP service is available for clients to connect to.
