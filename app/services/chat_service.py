"""ChatService — orchestrates a single /chat turn.

Depends only on ports, never on concrete adapters. The flow:
persist user turn → run the agent (tools) → evaluate the draft → persist assistant turn +
eval → escalate if flagged → return the brief's response/eval/tools_called/session_id shape.
The request's DB session commits once, at the end, so the whole turn is atomic.
"""

from uuid import uuid4

from app.agents.agent_loop import AgentLoop
from app.agents.prompts import AGENT_SYSTEM
from app.agents.tool_registry import ToolRegistry
from app.domain.errors import AgentError
from app.domain.ports import (
    CatalogPort,
    EvalStorePort,
    EvaluatorPort,
    LLMPort,
    MemoryPort,
    NotifierPort,
    ReviewLogPort,
)
from app.models.chat import ChatData, ChatHistory, HistoryTurn, MemoryWipeResult
from app.settings import Settings
from app.tools.flag_for_human import FlagForHumanTool
from app.tools.get_user_memory import GetUserMemoryTool
from app.tools.search_catalog import SearchCatalogTool


class ChatService:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        catalog: CatalogPort,
        llm: LLMPort,
        evaluator: EvaluatorPort,
        evals: EvalStorePort,
        reviews: ReviewLogPort,
        notifier: NotifierPort,
        settings: Settings,
    ) -> None:
        self._memory = memory
        self._catalog = catalog
        self._llm = llm
        self._evaluator = evaluator
        self._evals = evals
        self._reviews = reviews
        self._notifier = notifier
        self._settings = settings

    async def handle(self, *, user_id: str, message: str, session_id: str | None) -> ChatData:
        session_id = session_id or str(uuid4())

        # 1. Persist the incoming user turn (so cross-session memory survives this request).
        await self._memory.append_message(
            user_id=user_id, session_id=session_id, role="user", content=message
        )

        # 2. Assemble per-request tools (user_id/session_id bound server-side) and run the agent.
        flag = FlagForHumanTool(
            self._reviews, self._notifier, user_id=user_id, session_id=session_id
        )
        registry = ToolRegistry(
            [
                GetUserMemoryTool(
                    self._memory, user_id, recent_window=self._settings.recent_turns_window
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

        # 3. Evaluate the draft against the grounding the tools returned.
        evaluation = await self._evaluator.evaluate(
            user_message=message, context=outcome.context, draft_answer=outcome.answer
        )

        # 4. Persist the assistant turn and its eval (linked by message id).
        assistant_turn = await self._memory.append_message(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=outcome.answer,
            tools_called=outcome.tools_called,
        )
        if assistant_turn.seq is None:  # defensive: flush always assigns an id
            raise AgentError("Failed to persist the assistant turn.")
        await self._evals.record(
            message_id=assistant_turn.seq,
            user_id=user_id,
            session_id=session_id,
            evaluation=evaluation,
        )

        # 5. Authoritative escalation: the threshold decides, then flag_for_human fires.
        if evaluation.flagged:
            await flag.escalate(
                reason=(
                    f"Low confidence: {evaluation.confidence:.2f} "
                    f"< {self._settings.flag_confidence_threshold:.2f}"
                ),
                evaluation=evaluation,
                message_id=assistant_turn.seq,
            )

        return ChatData(
            response=outcome.answer,
            eval=evaluation,
            tools_called=outcome.tools_called,
            session_id=session_id,
        )

    async def history(self, user_id: str) -> ChatHistory:
        turns = await self._memory.get_history(user_id)
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
        deleted = await self._memory.wipe_user(user_id)
        return MemoryWipeResult(user_id=user_id, deleted_rows=deleted)
