"""NullNotifier — the default NotifierPort.

A take-home doesn't have a real pager. This logs the escalation in a structured way
(the request-scoped JSON logger picks it up); the NotifierPort seam is where a Slack or
PagerDuty adapter would slot in at scale.
"""

import logging

from app.models.eval import EvalBlock

logger = logging.getLogger("sales_agent.review")


class NullNotifier:
    async def notify(
        self,
        *,
        user_id: str,
        session_id: str,
        reason: str,
        evaluation: EvalBlock | None = None,
    ) -> None:
        confidence = f"{evaluation.confidence:.2f}" if evaluation else "n/a"
        logger.warning(
            "flagged_for_human",
            extra={
                "json_fields": {
                    "event": "flagged_for_human",
                    "user_id": user_id,
                    "session_id": session_id,
                    "confidence": confidence,
                    "reason": reason,
                }
            },
        )
