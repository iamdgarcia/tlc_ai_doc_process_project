from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/agent", tags=["Agent"])

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

    service = ChatService(session)
    return ChatResponse(response=service.chat(request.message))
