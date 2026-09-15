from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.extraction import (
    BatchDocumentExtractionResponse,
    DocumentExtractionError,
    DocumentExtractionResponse,
)
from app.services.document_extraction import DocumentExtractionService

router = APIRouter(prefix="/documents", tags=["Extraccion"])


@router.post(
    "/extract",
    response_model=DocumentExtractionResponse,
    summary="Extract structured fields from a document",
)
async def extract_document(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
) -> DocumentExtractionResponse:
    """Extract structured data from an image or PDF and store the result."""

    service = DocumentExtractionService(session)
    return await service.extract_and_store(file)


@router.post(
    "/extract/batch",
    response_model=BatchDocumentExtractionResponse,
    summary="Extract and store several receipt documents",
)
async def extract_documents(
    files: Annotated[list[UploadFile], File()],
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> BatchDocumentExtractionResponse:
    """Process up to 20 documents and report failures independently."""

    if len(files) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Se pueden subir como máximo 20 tickets a la vez.",
        )

    service = DocumentExtractionService(session)
    results: list[DocumentExtractionResponse] = []
    errors: list[DocumentExtractionError] = []
    for file in files:
        try:
            results.append(await service.extract_and_store(file))
        except HTTPException as exc:
            errors.append(
                DocumentExtractionError(
                    document_name=file.filename or "uploaded_file",
                    error=str(exc.detail),
                )
            )
        except Exception as exc:  # noqa: BLE001 - one invalid file must not abort the batch
            errors.append(
                DocumentExtractionError(
                    document_name=file.filename or "uploaded_file",
                    error=(
                        f"Error inesperado ({type(exc).__name__}). "
                        "Consulta el log del servidor."
                    ),
                )
            )

    if errors:
        response.status_code = status.HTTP_207_MULTI_STATUS

    return BatchDocumentExtractionResponse(
        total=len(files),
        successful=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
    )
