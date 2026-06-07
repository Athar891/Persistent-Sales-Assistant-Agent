"""ChatService — orchestrates a single /chat turn.

Depends only on ports, never on concrete adapters. The flow:
persist user turn → run the agent (tools) → evaluate the draft → persist assistant turn +
eval → escalate if flagged → summarize. Each DB step runs in its own short transaction via
the UnitOfWork, so no database connection is held while the agent or evaluator waits on the
LLM — the long pole of a turn. The trade-off is deliberate: the turn is no longer one atomic
transaction. The user message is durably recorded before generation, and the assistant turn
+ its eval commit together afterwards.
"""

from uuid import uuid4

from app.agents.agent_loop import AgentLoop
from app.agents.prompts import AGENT_SYSTEM
from app.agents.tool_registry import ToolRegistry
from app.domain.errors import AgentError
from app.domain.ports import (
    CatalogPort,
    EvaluatorPort,
    LLMPort,
    NotifierPort,
    UnitOfWork,
)
from app.logging_config import get_logger
from app.memory.summarizer import Summarizer
from app.models.chat import ChatData, ChatHistory, HistoryTurn, MemoryWipeResult
from app.models.eval import EvalSummary
from app.settings import Settings
from app.tools.flag_for_human import FlagForHumanTool
from app.tools.get_user_memory import GetUserMemoryTool
from app.tools.search_catalog import SearchCatalogTool

logger = get_logger("sales_agent.chat")


class ChatService:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        catalog: CatalogPort,
        llm: LLMPort,
        evaluator: EvaluatorPort,
        notifier: NotifierPort,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._llm = llm
        self._evaluator = evaluator
        self._notifier = notifier
        self._settings = settings
        self._summarizer = Summarizer(
            llm,
            model=settings.summarizer_model,
            max_tokens=settings.summarizer_max_tokens,
            recent_window=settings.recent_turns_window,
            summarize_after=settings.summarize_after_turns,
        )

    async def handle(self, *, user_id: str, message: str, session_id: str | None) -> ChatData:
        session_id = session_id or str(uuid4())

        # 1. Persist the incoming user turn in its own short transaction, so the connection
        #    is back in the pool before the (slow) agent run begins.
        async with self._uow.begin() as repos:
            await repos.memory.append_message(
                user_id=user_id, session_id=session_id, role="user", content=message
            )

        # 2. Run the agent. Its DB-backed tools (get_user_memory reads, flag_for_human writes)
        #    each open their own short transaction, so the loop holds no connection between
        #    model round-trips. user_id/session_id are bound server-side, never by the model.
        flag = FlagForHumanTool(
            self._uow, self._notifier, user_id=user_id, session_id=session_id
        )
        registry = ToolRegistry(
            [
                GetUserMemoryTool(
                    self._uow, user_id, recent_window=self._settings.recent_turns_window
                ),
                SearchCatalogTool(self._catalog),
                flag,
            ]
        )
        agent = AgentLoop(
            self._llm,
            registry,
            model=self._settings.agent_model,
            max_tokens=self._settings.agent_max_tokens,
            max_iterations=self._settings.max_agent_iterations,
        )
        outcome = await agent.run(system=AGENT_SYSTEM, user_message=message)

        # 3. Evaluate the draft against the grounding the tools returned (no DB).
        result = await self._evaluator.evaluate(
            user_message=message, context=outcome.context, draft_answer=outcome.answer
        )
        evaluation = result.block

        # 4. Persist the assistant turn and (only a genuine) eval together (one short tx).
        async with self._uow.begin() as repos:
            assistant_turn = await repos.memory.append_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=outcome.answer,
                tools_called=outcome.tools_called,
            )
            if assistant_turn.seq is None:  # defensive: flush always assigns an id
                raise AgentError("Failed to persist the assistant turn.")
            if result.evaluated:  # a degraded eval is escalated below, not persisted or averaged
                await repos.evals.record(
                    message_id=assistant_turn.seq,
                    user_id=user_id,
                    session_id=session_id,
                    evaluation=evaluation,
                )

        # 5. Escalate: a failed evaluation always needs a human; otherwise the threshold decides.
        if not result.evaluated:
            await flag.escalate(
                reason="Evaluator returned no structured score; needs human review.",
                evaluation=evaluation,
                message_id=assistant_turn.seq,
            )
        elif evaluation.flagged:
            await flag.escalate(
                reason=(
                    f"Low confidence: {evaluation.confidence:.2f} "
                    f"< {self._settings.flag_confidence_threshold:.2f}"
                ),
                evaluation=evaluation,
                message_id=assistant_turn.seq,
            )

        # 6. Best-effort rolling summarization once history grows past the window.
        await self._maybe_summarize(user_id)

        return ChatData(
            response=outcome.answer,
            eval=evaluation,
            tools_called=outcome.tools_called,
            session_id=session_id,
        )

    async def _maybe_summarize(self, user_id: str) -> None:
        try:
            await self._summarizer.run(self._uow, user_id)
        except Exception:  # best-effort: a summary failure must not fail the turn
            logger.warning("summarization_failed", extra={"json_fields": {"user_id": user_id}})

    async def evals_summary(self, user_id: str) -> EvalSummary:
        async with self._uow.begin() as repos:
            agg = await repos.evals.aggregate(
                user_id, high_confidence_threshold=self._settings.flag_confidence_threshold
            )
        return EvalSummary(
            user_id=user_id,
            total_responses=agg.total,
            high_confidence=agg.high_confidence,
            high_confidence_pct=agg.high_confidence_pct,
            flagged=agg.flagged,
            avg_groundedness=agg.avg_groundedness,
            avg_relevance=agg.avg_relevance,
            avg_confidence=agg.avg_confidence,
        )

    async def history(self, user_id: str) -> ChatHistory:
        async with self._uow.begin() as repos:
            turns = await repos.memory.get_history(user_id)
        items = [
            HistoryTurn(
                seq=t.seq,
                session_id=t.session_id or "",
                role=t.role,
                content=t.content,
                tools_called=t.tools_called,
                created_at=t.created_at,
            )
            for t in turns
            if t.seq is not None and t.created_at is not None
        ]
        return ChatHistory(user_id=user_id, count=len(items), turns=items)

    async def wipe(self, user_id: str) -> MemoryWipeResult:
        async with self._uow.begin() as repos:
            deleted = await repos.memory.wipe_user(user_id)
        return MemoryWipeResult(user_id=user_id, deleted_rows=deleted)
