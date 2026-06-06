"""End-to-end API tests through the real ASGI stack (DI, middleware, envelope, errors).

The headline is cross-session memory: two POSTs with the same user_id but different
sessions, where the second provably reads the first from the database.
"""

from sqlalchemy import func, select

from app.db.models import HumanReviewLog
from app.domain.types import ToolResultPart
from tests.support import Harness


async def test_health_reports_real_db_check(harness: Harness) -> None:
    r = await harness.client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
    assert body["data"]["uptime_seconds"] >= 0
    assert r.headers["x-request-id"] == body["meta"]["request_id"]


async def test_catalog_is_enveloped_with_the_three_plans(harness: Harness) -> None:
    r = await harness.client.get("/catalog")
    assert r.status_code == 200
    body = r.json()
    assert [p["name"] for p in body["data"]["plans"]] == ["Starter", "Growth", "Enterprise"]
    assert {"request_id", "timestamp", "latency_ms"} <= set(body["meta"])


async def test_chat_keeps_the_brief_contract_inside_the_envelope(harness: Harness) -> None:
    r = await harness.client.post("/chat/acme", json={"message": "enterprise pricing?"})
    assert r.status_code == 200
    payload = r.json()
    data = payload["data"]
    assert set(data) == {"response", "eval", "tools_called", "session_id"}
    assert set(data["eval"]) == {"groundedness", "relevance", "confidence", "flagged", "reasoning"}
    assert data["tools_called"] == ["get_user_memory", "search_catalog"]
    assert "$499" in data["response"]
    assert data["eval"]["flagged"] is False
    assert payload["meta"]["session_id"] == data["session_id"]


async def test_cross_session_memory_persists_across_calls(harness: Harness) -> None:
    r1 = await harness.client.post(
        "/chat/acme", json={"message": "What's your enterprise pricing?"}
    )
    s1 = r1.json()["data"]["session_id"]

    before = len(harness.llm.calls)
    r2 = await harness.client.post("/chat/acme", json={"message": "Does that include SSO?"})
    s2 = r2.json()["data"]["session_id"]

    assert s1 != s2  # two independent sessions, same user_id

    # In the SECOND request, get_user_memory surfaced the FIRST call's question from the DB.
    call2_tool_results = [
        part.content
        for call in harness.llm.calls[before:]
        for msg in call["messages"]
        for part in msg.parts
        if isinstance(part, ToolResultPart)
    ]
    assert any("enterprise pricing" in c.lower() for c in call2_tool_results)

    # History spans both sessions for the same user.
    history = (await harness.client.get("/chat/acme/history")).json()["data"]
    assert history["count"] == 4  # 2 user + 2 assistant turns
    assert {t["session_id"] for t in history["turns"]} == {s1, s2}


async def test_delete_memory_is_a_gdpr_reset(harness: Harness) -> None:
    await harness.client.post("/chat/acme", json={"message": "hello"})
    deleted = await harness.client.delete("/chat/acme/memory")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_rows"] >= 2

    history = (await harness.client.get("/chat/acme/history")).json()["data"]
    assert history["count"] == 0


async def test_low_confidence_flags_and_writes_a_review_row(harness: Harness) -> None:
    harness.llm.confidence = 0.3  # below the 0.7 threshold → must flag
    r = await harness.client.post("/chat/acme", json={"message": "something ambiguous"})
    assert r.json()["data"]["eval"]["flagged"] is True

    async with harness.db.sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(HumanReviewLog))
    assert count == 1


async def test_validation_error_is_problem_json(harness: Harness) -> None:
    r = await harness.client.post("/chat/acme", json={"message": ""})  # violates min_length=1
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 422
    assert body["title"] == "Unprocessable Entity"
    assert body["request_id"]


async def test_unknown_route_is_problem_json(harness: Harness) -> None:
    r = await harness.client.get("/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 404
