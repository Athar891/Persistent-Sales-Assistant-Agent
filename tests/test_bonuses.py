"""Bonus endpoints: GET /chat/{user_id}/evals aggregation and GET /reviews queue."""

from tests.support import Harness


async def test_evals_aggregation_is_a_real_query(harness: Harness) -> None:
    await harness.client.post("/chat/acme", json={"message": "a"})
    await harness.client.post("/chat/acme", json={"message": "b"})

    data = (await harness.client.get("/chat/acme/evals")).json()["data"]
    assert data["total_responses"] == 2
    assert data["high_confidence"] == 2  # stubbed confidence 0.9 >= 0.7
    assert data["high_confidence_pct"] == 100.0
    assert data["flagged"] == 0
    assert 0.0 <= data["avg_confidence"] <= 1.0


async def test_evals_for_unknown_user_is_zeroed(harness: Harness) -> None:
    data = (await harness.client.get("/chat/nobody/evals")).json()["data"]
    assert data["total_responses"] == 0
    assert data["high_confidence_pct"] == 0.0


async def test_reviews_endpoint_lists_and_filters(harness: Harness) -> None:
    harness.llm.confidence = 0.3  # force a flag → a review row
    await harness.client.post("/chat/acme", json={"message": "ambiguous"})

    data = (await harness.client.get("/reviews")).json()["data"]
    assert data["count"] == 1
    entry = data["entries"][0]
    assert entry["user_id"] == "acme"
    assert entry["confidence"] == 0.3
    assert entry["resolved"] is False

    empty = (await harness.client.get("/reviews", params={"user_id": "nobody"})).json()["data"]
    assert empty["count"] == 0
