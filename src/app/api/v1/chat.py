from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.chat import ChatService

router = APIRouter(prefix="/agent", tags=["Agent"])

@router.post(
    "/chat",
    summary="Chat about stored tickets",
)
async def chat(
    message: str,
    session: Session = Depends(get_session),
) -> str:
    """Answer a question using data from stored tickets."""

    service = ChatService(session)
    return service.chat(message)
