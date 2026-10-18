"""Durable per-user conversation memory in PostgreSQL."""

from contextlib import asynccontextmanager

from langchain_core.messages import AIMessage, HumanMessage
from psycopg_pool import AsyncConnectionPool


class PostgresMemory:
    def __init__(self, pool: AsyncConnectionPool, recent_turns: int = 5):
        self.pool = pool
        self.recent_turns = recent_turns

    async def setup(self):
        async with self.pool.connection() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_message TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await connection.execute("""
                CREATE INDEX IF NOT EXISTS agent_memory_user_id_idx
                ON agent_memory (user_id, id DESC)
            """)

    async def load(self, user_id: str):
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT user_message, assistant_message FROM agent_memory "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, self.recent_turns),
            )
            rows = await cursor.fetchall()
        messages = []
        # Bound recalled context without truncating the durable records.
        for question, answer in reversed(rows):
            messages.extend([
                HumanMessage(content=question[:1200]),
                AIMessage(content=answer[:1200]),
            ])
        return messages

    async def save(self, user_id: str, question: str, answer: str):
        async with self.pool.connection() as connection:
            await connection.execute(
                "INSERT INTO agent_memory (user_id, user_message, assistant_message) "
                "VALUES (%s, %s, %s)", (user_id, question, answer),
            )


@asynccontextmanager
async def memory_runtime(database_url: str, recent_turns: int):
    async with AsyncConnectionPool(
        database_url, min_size=1, max_size=5, open=False,
        timeout=10, kwargs={"connect_timeout": 5},
    ) as pool:
        await pool.wait(timeout=10)
        memory = PostgresMemory(pool, recent_turns)
        await memory.setup()
        yield memory
