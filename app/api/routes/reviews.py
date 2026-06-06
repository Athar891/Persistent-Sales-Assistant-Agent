"""GET /reviews — the human-reviewer queue for flagged responses (bonus).

Optional filters: ?user_id=… and ?unresolved=true.
"""

from fastapi import APIRouter, Request

from app.api.deps import ReviewLogDep
from app.api.responses import build_meta
from app.models.envelope import Envelope
from app.models.review import ReviewLog, ReviewLogEntry

router = APIRouter(tags=["reviews"])


@router.get("/reviews", response_model=Envelope[ReviewLog])
async def list_reviews(
    request: Request,
    reviews: ReviewLogDep,
    user_id: str | None = None,
    unresolved: bool = False,
    limit: int = 100,
) -> Envelope[ReviewLog]:
    entries = await reviews.list_entries(user_id=user_id, only_unresolved=unresolved, limit=limit)
    items = [ReviewLogEntry.model_validate(e, from_attributes=True) for e in entries]
    data = ReviewLog(count=len(items), entries=items)
    return Envelope[ReviewLog](data=data, meta=build_meta(request))
