"""The agent loop must use *real* tools and feed their results back to the model
(rubric: tool use is real — search_catalog actually searches, get_user_memory queries the DB).
"""

from pathlib import Path

import pytest

from app.agents.agent_loop import AgentLoop
from app.agents.tool_registry import ToolRegistry
from app.catalog.keyword_search import KeywordCatalogSearch
from app.db.session import Database
from app.db.unit_of_work import SqlUnitOfWork
from app.domain.types import ToolResultPart
from app.memory.sql_store import SqlMemoryStore
from app.tools.get_user_memory import GetUserMemoryTool
from app.tools.search_catalog import SearchCatalogTool
from tests.support import ScriptedLLM, final_text, tool_use

CATALOG = str(Path(__file__).resolve().parents[1] / "catalog.json")


@pytest.fixture
def db_url(tmp_path: object) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/agent.db"  # type: ignore[operator]


async def test_agent_calls_real_tools_and_feeds_results_back(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    # Seed a prior session so get_user_memory has something real to recall.
    async with db.sessionmaker() as session:
        memory = SqlMemoryStore(session)
        await memory.append_message(
            user_id="acme", session_id="s0", role="user",
            content="What's your enterprise pricing?",
        )
        await memory.append_message(
            user_id="acme", session_id="s0", role="assistant",
            content="Enterprise is $499/mo.", tools_called=["search_catalog"],
        )
        await session.commit()

    # The tool reads through its own short transactions (a UnitOfWork over the same engine).
    registry = ToolRegistry(
        [
            GetUserMemoryTool(SqlUnitOfWork(db.sessionmaker), "acme", recent_window=6),
            SearchCatalogTool(KeywordCatalogSearch.from_file(CATALOG)),
        ]
    )
    llm = ScriptedLLM(
        [
            tool_use("t1", "get_user_memory", {}),
            tool_use("t2", "search_catalog", {"query": "enterprise sso"}),
            final_text("Yes — the Enterprise plan ($499/mo) includes SSO and audit logs."),
        ]
    )
    loop = AgentLoop(llm, registry, model="m", max_tokens=256, max_iterations=6)
    outcome = await loop.run(system="sys", user_message="Does enterprise include SSO?")
    await db.dispose()

    assert outcome.tools_called == ["get_user_memory", "search_catalog"]
    assert "$499" in outcome.answer
    assert "SSO" in outcome.answer

    # Everything the tools returned must have been fed back to the model as tool_results.
    fed_back = [
        part.content
        for call in llm.calls
        for msg in call["messages"]
        for part in msg.parts
        if isinstance(part, ToolResultPart)
    ]
    assert any("Enterprise — $499/mo" in c for c in fed_back)  # search_catalog result
    assert any("enterprise pricing" in c.lower() for c in fed_back)  # recalled prior turn
    # The grounding context handed to the evaluator carries the same tool output.
    assert "Enterprise — $499/mo" in outcome.context


async def test_agent_returns_directly_when_model_ends_turn(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    registry = ToolRegistry(
        [
            GetUserMemoryTool(SqlUnitOfWork(db.sessionmaker), "u", recent_window=6),
            SearchCatalogTool(KeywordCatalogSearch.from_file(CATALOG)),
        ]
    )
    llm = ScriptedLLM([final_text("Hi! Happy to help with our plans.")])
    loop = AgentLoop(llm, registry, model="m", max_tokens=256, max_iterations=6)
    outcome = await loop.run(system="sys", user_message="hi")
    await db.dispose()

    assert outcome.tools_called == []
    assert "help" in outcome.answer.lower()


async def test_agent_recovers_from_a_failing_tool(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()

    class BoomTool:
        name = "search_catalog"

        @property
        def spec(self):  # type: ignore[no-untyped-def]
            from app.domain.types import ToolSpec

            return ToolSpec(name=self.name, description="boom", input_schema={"type": "object"})

        async def run(self, arguments: dict[str, object]) -> str:
            raise RuntimeError("catalog unavailable")

    registry = ToolRegistry(
        [BoomTool(), GetUserMemoryTool(SqlUnitOfWork(db.sessionmaker), "u", recent_window=6)]
    )
    llm = ScriptedLLM(
        [
            tool_use("t1", "search_catalog", {"query": "x"}),
            final_text("Sorry, I can't reach the catalog right now."),
        ]
    )
    loop = AgentLoop(llm, registry, model="m", max_tokens=256, max_iterations=6)
    outcome = await loop.run(system="sys", user_message="prices?")
    await db.dispose()

    # The loop survived the tool exception and surfaced an error tool_result to the model.
    fed_back = [
        part.content
        for call in llm.calls
        for msg in call["messages"]
        for part in msg.parts
        if isinstance(part, ToolResultPart)
    ]
    assert any("Error running search_catalog" in c for c in fed_back)
    assert "catalog" in outcome.answer.lower()
