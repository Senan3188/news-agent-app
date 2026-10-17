import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from news_agent.mcp_server import mcp
from news_agent.news import NewsRequest, NewsResult, get_latest_news, parse_news

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def feed(*items):
    return ("<rss version='2.0'><channel><title>News</title>" + "".join(
        f"<item><title>{title}</title><link>{url}</link><pubDate>{date}</pubDate>"
        "<source>Publisher</source><description>&lt;b&gt;Summary&lt;/b&gt;</description></item>"
        for title, url, date in items
    ) + "</channel></rss>").encode()


def test_mapping_sorting_filtering_and_deduplication():
    recent = ("Recent", "https://example.com/new", "Sat, 17 Oct 2026 11:00:00 GMT")
    content = feed(
        ("Older", "https://example.com/older", "Sat, 17 Oct 2026 10:00:00 GMT"),
        recent, recent,
        ("Stale", "https://example.com/stale", "Thu, 15 Oct 2026 10:00:00 GMT"),
        ("Future", "https://example.com/future", "Sun, 18 Oct 2026 10:00:00 GMT"),
        ("Bad URL", "javascript:alert(1)", recent[2]),
        ("Missing date", "https://example.com/missing", "invalid"),
    )
    result = parse_news(content, NewsRequest(), NOW)
    assert [a.title for a in result.articles] == ["Recent", "Older"]
    assert result.articles[0].summary == "Summary"
    assert result.articles[0].source == "Publisher"
    assert result.articles[0].published_at.tzinfo == timezone.utc
    assert len(parse_news(content, NewsRequest(limit=1), NOW).articles) == 1
    assert NewsResult.model_validate_json(result.model_dump_json()) == result


def test_invalid_feed_and_arguments():
    with pytest.raises(ValueError, match="invalid RSS"):
        parse_news(b"<html>Error</html>", NewsRequest(), NOW)
    for values in ({"limit": 0}, {"limit": 51}, {"max_age_hours": 0}):
        with pytest.raises(ValidationError):
            NewsRequest(**values)


def test_fetch_and_provider_failure(monkeypatch):
    async def get(self, url, params):
        assert url.endswith("/search")
        assert params["q"] == "AI when:24h"
        return httpx.Response(200, content=feed(), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    assert asyncio.run(get_latest_news("AI")).articles == []

    async def fail(self, url, params):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", fail)
    with pytest.raises(RuntimeError, match="Unable to retrieve"):
        asyncio.run(get_latest_news())


def test_mcp_structured_output(monkeypatch):
    async def get(self, url, params):
        return httpx.Response(200, content=feed(), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    async def check():
        tools = await mcp.list_tools()
        tool = next(tool for tool in tools if tool.name == "get_latest_news")
        assert "articles" in tool.outputSchema["properties"]
        _, structured = await mcp.call_tool("get_latest_news", {"query": "AI"})
        assert NewsResult.model_validate(structured).query == "AI"

    asyncio.run(check())
