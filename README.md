# News Agent App

Install dependencies with `uv sync`.

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
