"""FastAPI interface for the local Ollama news agent."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field, StringConstraints

from news_agent.agent import agent_runtime
from news_agent.config import Settings
from news_agent.news import NewsResult

logger = logging.getLogger(__name__)


class AgentRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class AgentResponse(BaseModel):
    answer: str
    model: str
    news_results: list[NewsResult] = Field(default_factory=list)


def create_app(settings: Settings | None = None, runtime_factory=agent_runtime) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with runtime_factory(settings) as graph:
            app.state.graph = graph
            yield

    app = FastAPI(title="News Agent API", lifespan=lifespan)

    @app.post("/agent", response_model=AgentResponse)
    async def run_agent(body: AgentRequest, request: Request) -> AgentResponse:
        try:
            async with asyncio.timeout(settings.agent_timeout_seconds):
                state = await request.app.state.graph.ainvoke(
                    {"messages": [HumanMessage(content=body.message)]},
                    config={"recursion_limit": settings.agent_recursion_limit},
                )
            final = state["messages"][-1]
            if not isinstance(final, AIMessage) or final.tool_calls or not final.text.strip():
                raise ValueError("Agent did not produce a final answer")
            results = []
            for message in state["messages"]:
                if isinstance(message, ToolMessage) and message.name == "get_latest_news":
                    artifact = message.artifact or {}
                    results.append(NewsResult.model_validate(artifact["structured_content"]))
            return AgentResponse(answer=final.text, model=settings.ollama_model, news_results=results)
        except TimeoutError as exc:
            raise HTTPException(504, "Agent request timed out") from exc
        except GraphRecursionError as exc:
            raise HTTPException(502, "Agent exceeded its tool-call step limit") from exc
        except Exception as exc:
            logger.exception("News agent request failed")
            raise HTTPException(
                502, "Agent failed. Check Ollama, the installed model, and the news provider."
            ) from exc

    return app


app = create_app()
