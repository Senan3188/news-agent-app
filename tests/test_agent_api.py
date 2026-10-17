import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import sys

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.errors import GraphRecursionError

from news_agent.agent import build_graph
from news_agent.api import create_app
from news_agent.config import PROJECT_ROOT, Settings
from news_agent.news import NewsResult


def test_graph_calls_tool_then_returns_to_model():
    calls = []

    @tool
    async def get_latest_news(query: str) -> str:
        """Get news about a topic."""
        calls.append(query)
        return "Verified news"

    class Model:
        def bind_tools(self, tools):
            assert tools[0].name == "get_latest_news"
            return self

        async def ainvoke(self, messages):
            if isinstance(messages[-1], ToolMessage):
                assert messages[-1].content == "Verified news"
                return AIMessage(content="Here is the news")
            return AIMessage(content="", tool_calls=[{
                "name": "get_latest_news", "args": {"query": "AI"}, "id": "news-1"
            }])

    result = asyncio.run(build_graph(Model(), [get_latest_news]).ainvoke(
        {"messages": [("user", "Get AI news")]}
    ))
    assert calls == ["AI"]
    assert result["messages"][-1].content == "Here is the news"


def runtime_for(graph):
    @asynccontextmanager
    async def runtime(settings):
        yield graph
    return runtime


def test_api_response_and_request_isolation():
    news = NewsResult(query="AI", fetched_at=datetime.now(timezone.utc), articles=[])

    class Graph:
        async def ainvoke(self, state, config):
            assert len(state["messages"]) == 1
            assert config["recursion_limit"] == 12
            return {"messages": [ToolMessage(
                content="news", name="get_latest_news", tool_call_id="1",
                artifact={"structured_content": news.model_dump(mode="json")},
            ), AIMessage(content="No recent articles.")]}

    with TestClient(create_app(Settings(), runtime_for(Graph()))) as client:
        for _ in range(2):
            response = client.post("/agent", json={"message": "Get AI news"})
            assert response.status_code == 200
            assert response.json()["model"] == "qwen3:8b"
            assert response.json()["news_results"][0]["query"] == "AI"
        for message in ("", "   ", "x" * 8001):
            assert client.post("/agent", json={"message": message}).status_code == 422


def test_api_failure_responses():
    for error, code in ((RuntimeError("private details"), 502),
                        (GraphRecursionError("loop"), 502), (TimeoutError(), 504)):
        class Graph:
            async def ainvoke(self, state, config):
                raise error

        with TestClient(create_app(Settings(), runtime_for(Graph()))) as client:
            response = client.post("/agent", json={"message": "News?"})
            assert response.status_code == code
            assert "private details" not in response.text


def test_api_deadline_cancels_slow_graph():
    class Graph:
        async def ainvoke(self, state, config):
            await asyncio.sleep(10)

    settings = Settings(agent_timeout_seconds=0.01)
    with TestClient(create_app(settings, runtime_for(Graph()))) as client:
        response = client.post("/agent", json={"message": "News?"})
        assert response.status_code == 504


def test_real_mcp_subprocess_discovery():
    async def check():
        client = MultiServerMCPClient({"news": {
            "transport": "stdio", "command": sys.executable,
            "args": ["-m", "news_agent.mcp_server"], "cwd": str(PROJECT_ROOT),
        }})
        async with client.session("news") as session:
            tools = await load_mcp_tools(session, handle_tool_errors=False)
            assert [t.name for t in tools] == ["get_latest_news"]
            assert "query" in tools[0].args

    asyncio.run(check())
