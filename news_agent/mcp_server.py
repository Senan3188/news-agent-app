"""Run with: uv run python -m news_agent.mcp_server [--http]."""

import argparse

from mcp.server.fastmcp import FastMCP

from news_agent.news import get_latest_news

mcp = FastMCP("news-agent", host="127.0.0.1", port=8000, json_response=True)
mcp.tool()(get_latest_news)


def main() -> None:
    parser = argparse.ArgumentParser(description="News MCP service")
    parser.add_argument("--http", action="store_true", help="Serve at http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
