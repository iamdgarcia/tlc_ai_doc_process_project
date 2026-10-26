from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/agent", tags=["Agent"])


def get_chat_service(session: Session = Depends(get_session)) -> ChatService:
    """One ChatService per request: ni conversaciones ni sesiones compartidas."""
    return ChatService(session=session)


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat about stored tickets",
)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Answer a question using data from stored tickets."""

    # ponytail: el SDK de OpenAI es síncrono; sin el threadpool bloquea el event
    # loop hasta 8 roundtrips y sativa uploads/dashboard/health.
    answer = await run_in_threadpool(service.chat, request.message)
    return ChatResponse(response=answer)


@router.delete(
    "/chat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset the chat conversation",
)
async def reset_chat() -> Response:
    """Clear the conversation history kept by the chat agent.

    Cada petición construye su propio ChatService (no hay conversación
    compartida en el servidor), así que el reset se mantiene por
    compatibilidad con el dashboard y es una no-op.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
