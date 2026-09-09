from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService
router = APIRouter(prefix="/agent", tags=["Agent"])
service = ChatService()
@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat about stored tickets",
)
async def chat(
    request: ChatRequest,
    session: Session = Depends(get_session),
) -> ChatResponse:
    """Answer a question using data from stored tickets."""

    service.set_session(session)
    response = ChatResponse(response=service.chat(request.message))
    return response


@router.delete(
    "/chat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset the chat conversation",
)
async def reset_chat() -> Response:
    """Clear the conversation history kept by the chat agent."""

    service.reset_conversation()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
