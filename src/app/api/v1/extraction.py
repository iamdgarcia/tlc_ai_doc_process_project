from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.extraction import DocumentExtractionResponse
from app.services.document_extraction import DocumentExtractionService

router = APIRouter(prefix="/documents", tags=["Extraccion"])


@router.post(
    "/extract",
    response_model=DocumentExtractionResponse,
    summary="Extract structured fields from a document",
)
async def extract_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> DocumentExtractionResponse:
    """Extract structured data from an image or PDF and store the result."""

    service = DocumentExtractionService(session)
    return await service.extract_and_store(file)
