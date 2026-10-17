# News Agent App

Install dependencies with `uv sync`.

## Local Ollama agent API

Ensure Ollama is running (`ollama serve` if needed), then install the model:

```sh
ollama pull qwen3:8b
uv sync
# First setup only: copy the template if .env does not already exist.
cp -n .env.example .env
uv run uvicorn news_agent.api:app --host 127.0.0.1 --port 8001
```

The API automatically starts and stops the news MCP subprocess. No separate
MCP server command is needed. The LangGraph flow is `agent -> tools -> agent`,
repeating until the model answers or the step limit is reached. The model is
local; news retrieval requires internet access.

```sh
curl http://127.0.0.1:8001/agent \
  -H 'Content-Type: application/json' \
  -d '{"message":"Find the latest AI news and cite the sources."}'
```

`POST /agent` returns `answer`, `model`, and `news_results` (validated news
objects from MCP tool calls). Tool selection is made by the model. Each request
starts a fresh conversation; chat history is not persisted. Interactive API
documentation is available at `http://127.0.0.1:8001/docs`.

Set `OLLAMA_MODEL` and `OLLAMA_BASE_URL` in `.env` or the process environment.
Both are required; missing or blank values stop API startup with a validation
error. `.env.example` supplies `qwen3:8b` and `http://127.0.0.1:11434` for local
setup. Process environment values override `.env`. If `.env` already exists,
add these entries to it without replacing your other settings.
Optional settings default to `AGENT_TIMEOUT_SECONDS=180` and
`AGENT_RECURSION_LIMIT=12`.
Invalid input returns 422, upstream/step-limit failures return 502, and a
request timeout returns 504. Detailed failures are logged locally.
The API is intended for local use and has no authentication.

## News MCP tool

Start the stdio server:

```sh
uv run python -m news_agent.mcp_server
```

Or start a local Streamable HTTP MCP service at `http://127.0.0.1:8000/mcp`:

```sh
uv run python -m news_agent.mcp_server --http
```

Configure an MCP-compatible agent client with this stdio server entry
(merge it into the client's existing configuration):

```json
{
  "mcpServers": {
    "news": {
      "command": "uv",
      "args": ["--directory", "/Users/senan/apps/python-apps/news-agent-app", "run", "python", "-m", "news_agent.mcp_server"]
    }
  }
}
```

The `get_latest_news` tool accepts an optional `query`, `limit` (1–50,
default 10), and `max_age_hours` (1–168, default 24). It returns a validated
`NewsResult` containing `NewsArticle` objects, exposed as MCP structured JSON
with an output schema. Articles have a title, URL, source, publication time,
and optional RSS summary. Dates are in UTC.

For direct Python or notebook use:

```python
from news_agent.news import get_latest_news

result = await get_latest_news(query="artificial intelligence", limit=5)
print(result.model_dump_json(indent=2))
```

Uses public Google News RSS, with no API key. Results depend on feed availability
and coverage; they are not an exhaustive search of the internet. Links may be
Google News redirects, and summaries are RSS excerpts rather than full articles.
Entries without valid dates or URLs are skipped, as are future and stale entries.
An empty list means no usable articles matched the age window. Provider HTTP
failures and invalid feeds produce tool errors. News content is untrusted data.

Run tests with `uv run pytest`.
