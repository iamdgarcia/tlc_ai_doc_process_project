from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_session
from app.models.job import Job
from app.schemas.extraction import (
    BatchDocumentExtractionResponse,
    DocumentExtractionError,
    DocumentExtractionResponse,
)
from app.services.document_extraction import DocumentExtractionService, read_capped_upload


class _BytesUploadFile:
    """Minimal UploadFile stand-in backed by in-memory bytes."""

    def __init__(self, filename: str, content_type: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._data
        return self._data[:size]


async def _process_job(job_id: str, filename: str, content_type: str, data: bytes) -> None:
    """Background task: extract one document and update job status."""
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = "processing"
        session.commit()
        try:
            file = _BytesUploadFile(filename, content_type, data)
            service = DocumentExtractionService(session)
            result = await service.extract_and_store(file)  # type: ignore[arg-type]
            job.status = "done"
            job.ticket_id = result.stored_document_id
        except HTTPException as exc:
            job.status = "failed"
            job.error = str(exc.detail)[:500]
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:500]
        session.commit()

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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


@router.post(
    "/extract/batch/async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue several documents for background extraction",
)
async def extract_documents_async(
    files: Annotated[list[UploadFile], File()],
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """Accept files immediately, process them in the background. Poll /api/v1/jobs/batch/{batch_id}."""

    if len(files) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Se pueden subir como máximo 20 tickets a la vez.",
        )

    batch_id = str(uuid.uuid4())
    queued: list[tuple[str, str, str, bytes]] = []

    for file in files:
        data = await read_capped_upload(file)  # 413 si supera el límite por archivo
        job = Job(
            id=str(uuid.uuid4()),
            batch_id=batch_id,
            filename=file.filename or "uploaded_file",
            status="pending",
        )
        session.add(job)
        session.flush()
        queued.append((job.id, job.filename, file.content_type or "application/octet-stream", data))

    session.commit()

    for job_id, filename, content_type, data in queued:
        background_tasks.add_task(_process_job, job_id, filename, content_type, data)

    return {
        "batch_id": batch_id,
        "total": len(queued),
        "jobs": [{"job_id": jid, "filename": fname, "status": "pending"} for jid, fname, _, _ in queued],
    }
