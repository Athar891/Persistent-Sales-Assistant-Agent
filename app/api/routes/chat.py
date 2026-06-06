"""Chat endpoints. Handlers stay dumb: parse, delegate to ChatService, serialize."""

from fastapi import APIRouter, Request

from app.api.deps import ChatServiceDep
from app.api.responses import build_meta
from app.models.chat import ChatData, ChatHistory, ChatRequest, MemoryWipeResult
from app.models.envelope import Envelope

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/{user_id}", response_model=Envelope[ChatData])
async def chat(
    user_id: str, body: ChatRequest, request: Request, service: ChatServiceDep
) -> Envelope[ChatData]:
    data = await service.handle(
        user_id=user_id, message=body.message, session_id=body.session_id
    )
    # Surface tools + eval scores to the per-request structured log line.
    request.state.log_fields = {"tools_called": data.tools_called, "eval": data.eval.model_dump()}
    return Envelope[ChatData](data=data, meta=build_meta(request, session_id=data.session_id))


@router.get("/{user_id}/history", response_model=Envelope[ChatHistory])
async def history(
    user_id: str, request: Request, service: ChatServiceDep
) -> Envelope[ChatHistory]:
    return Envelope[ChatHistory](data=await service.history(user_id), meta=build_meta(request))


@router.delete("/{user_id}/memory", response_model=Envelope[MemoryWipeResult])
async def wipe_memory(
    user_id: str, request: Request, service: ChatServiceDep
) -> Envelope[MemoryWipeResult]:
    return Envelope[MemoryWipeResult](data=await service.wipe(user_id), meta=build_meta(request))
