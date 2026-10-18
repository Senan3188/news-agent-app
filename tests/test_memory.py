import asyncio
import os
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from news_agent.agent import build_graph
from news_agent.memory import memory_runtime


class FakeMemory:
    def __init__(self):
        self.turns = {}

    async def load(self, user_id):
        return list(self.turns.get(user_id, []))

    async def save(self, user_id, question, answer):
        self.turns.setdefault(user_id, []).extend([
            HumanMessage(content=question), AIMessage(content=answer),
        ])


def test_memory_recalled_for_same_user_only():
    class Model:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            prior = [m.content for m in messages[1:-1]]
            return AIMessage(content="I remember Brussels" if "I live in Brussels" in prior else "Noted")

    async def check():
        memory = FakeMemory()
        graph = build_graph(Model(), [], memory)
        async def ask(user, question):
            return await graph.ainvoke({"user_id": user, "messages": [("user", question)]})
        await ask("alice", "I live in Brussels")
        result = await ask("alice", "Where do I live?")
        assert result["messages"][-1].text == "I remember Brussels"
        result = await ask("bob", "Where do I live?")
        assert result["messages"][-1].text == "Noted"
        assert len(result["messages"]) == 2  # no old tool results leak into this response

    asyncio.run(check())


def test_failed_generation_is_not_saved():
    class Model:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("generation failed")

    async def check():
        memory = FakeMemory()
        with pytest.raises(RuntimeError):
            await build_graph(Model(), [], memory).ainvoke({
                "user_id": "alice", "messages": [("user", "remember this")],
            })
        assert memory.turns == {}

    asyncio.run(check())


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL for PostgreSQL integration")
def test_postgres_persistence_across_pools():
    async def check():
        url = os.environ["TEST_DATABASE_URL"]
        user = str(uuid4())
        async with memory_runtime(url, 2) as memory:
            await memory.save(user, "old", "old answer")
            await memory.save(user, "I live in Brussels", "Noted")
            await memory.save(user, "latest", "latest answer")
        # Reopen all connections, as after an API restart.
        async with memory_runtime(url, 2) as memory:
            messages = await memory.load(user)
            assert [m.text for m in messages] == [
                "I live in Brussels", "Noted", "latest", "latest answer",
            ]
            assert await memory.load(user + "other") == []
            await memory.save(user + "' OR 1=1 --", "literal ID", "answer")
            assert await memory.load(user + "other") == []
            async with memory.pool.connection() as conn:
                await conn.execute("DELETE FROM agent_memory WHERE user_id = %s OR user_id = %s",
                                   (user, user + "' OR 1=1 --"))

    asyncio.run(check())
