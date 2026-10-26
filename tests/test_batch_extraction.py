import asyncio
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException, Response, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.extraction import _process_job, extract_documents
from app.main import app
from app.models import Base, Job, Ticket
from app.schemas.extraction import (
    DocumentExtractionResponse,
    ProductoCantidadExtraction,
    StructuredExtraction,
    SupermercadoExtraction,
)
from app.services.document_extraction import DocumentExtractionService


def _fake_extract_factory(ticket_id: str):
    async def fake_extract(data: bytes, content_type: str) -> StructuredExtraction:
        return StructuredExtraction(
            id_ticket=ticket_id,
            supermercado=SupermercadoExtraction(nombre_supermercado="mercadona"),
            dia="2026-05-26",
            hora="12:00",
            total=12.5,
            productos=[
                ProductoCantidadExtraction(
                    nombre_producto="pan", cantidad="1", precio=1.10
                )
            ],
        )

    return fake_extract


def _job_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_batch_extraction_reports_success_and_failure(monkeypatch) -> None:
    async def fake_extract(self, file: UploadFile) -> DocumentExtractionResponse:
        if file.filename == "bad.pdf":
            raise HTTPException(status_code=422, detail="Ticket ilegible")
        extraction = StructuredExtraction(
            id_ticket="T-BATCH-1",
            supermercado=SupermercadoExtraction(nombre_supermercado="mercadona"),
            dia="2026-05-26",
            hora="12:00",
            total=12.5,
            productos=[],
        )
        return DocumentExtractionResponse(
            document_name=file.filename or "uploaded_file",
            content_type=file.content_type or "application/pdf",
            stored_document_id="T-BATCH-1",
            message="Document processed successfully",
            extraction=extraction,
        )

    monkeypatch.setattr(
        "app.api.v1.extraction.DocumentExtractionService.extract_and_store",
        fake_extract,
    )
    files = [
        UploadFile(BytesIO(b"ok"), filename="ok.pdf"),
        UploadFile(BytesIO(b"bad"), filename="bad.pdf"),
    ]

    response = Response()
    result = asyncio.run(
        extract_documents(files=files, session=None, response=response)
    )

    assert result.total == 2
    assert result.successful == 1
    assert result.failed == 1
    assert result.results[0].document_name == "ok.pdf"
    assert result.errors[0].document_name == "bad.pdf"
    assert result.errors[0].error == "Ticket ilegible"
    assert response.status_code == 207


def test_process_job_completes_a_small_file(monkeypatch) -> None:
    """Regression: sin cursor en _BytesUploadFile, un doc de 10KB acumulaba el
    primer trozo en bucle hasta "superar" 10MB y moría con 413."""
    engine = _job_engine()
    TestingSessionLocal = sessionmaker(bind=engine)

    async def fake_extract(data: bytes, content_type: str) -> StructuredExtraction:
        return StructuredExtraction(
            id_ticket="T-JOB-1",
            supermercado=SupermercadoExtraction(nombre_supermercado="mercadona"),
            dia="2026-05-26",
            hora="12:00",
            total=12.5,
            productos=[
                ProductoCantidadExtraction(
                    nombre_producto="pan", cantidad="1", precio=1.10
                )
            ],
        )

    monkeypatch.setattr("app.services.document_extraction.extract_ticket", fake_extract)
    monkeypatch.setattr("app.api.v1.extraction.SessionLocal", TestingSessionLocal)
    with TestingSessionLocal() as session:
        session.add(
            Job(id="job-1", batch_id="b1", filename="ticket.jpg", status="pending")
        )
        session.commit()

    asyncio.run(_process_job("job-1", "ticket.jpg", "image/jpeg", b"x" * 10240))

    with TestingSessionLocal() as session:
        job = session.get(Job, "job-1")
        assert job.status == "done"
        assert job.ticket_id == "T-JOB-1"
        assert session.get(Ticket, "T-JOB-1") is not None  # el resultado quedó guardado


def test_async_batch_endpoint_processes_a_small_file(seeded_engine, api_client, monkeypatch) -> None:
    """End to end: el endpoint encola, la background task extrae y guarda."""
    monkeypatch.setattr(
        "app.services.document_extraction.extract_ticket",
        _fake_extract_factory("T-JOB-ASYNC"),
    )
    TestingSessionLocal = sessionmaker(
        bind=seeded_engine, autocommit=False, autoflush=False
    )
    # _process_job usa el SessionLocal de módulo: apuntarlo a la MISMA BD que la request.
    monkeypatch.setattr("app.api.v1.extraction.SessionLocal", TestingSessionLocal)

    with patch("app.main.MASTER_KEY", "test-master-key"):
        response = api_client.post(
            "/api/v1/documents/extract/batch/async",
            files=[("files", ("small.jpg", b"x" * 10240, "image/jpeg"))],
            headers={"Authorization": "Bearer test-master-key"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 1
    with TestingSessionLocal() as session:
        job = session.get(Job, body["jobs"][0]["job_id"])
        assert job.status == "done"
        assert job.ticket_id == "T-JOB-ASYNC"
        assert session.get(Ticket, "T-JOB-ASYNC") is not None


def test_extraction_exposes_safe_unexpected_error(monkeypatch) -> None:
    class MemoryUpload:
        filename = "ticket.jpg"
        content_type = "image/jpeg"

        def __init__(self) -> None:
            self._cursor = 0

        async def read(self, size: int = -1) -> bytes:
            data = b"image"
            if size is None or size < 0:
                self._cursor = len(data)
                return data
            chunk = data[self._cursor : self._cursor + size]
            self._cursor += len(chunk)
            return chunk

    async def broken_extraction(*_):
        raise RuntimeError("provider response was invalid")

    monkeypatch.setattr(
        "app.services.document_extraction.extract_ticket",
        broken_extraction,
    )
    service = DocumentExtractionService(session=object())
    try:
        asyncio.run(service.extract_and_store(MemoryUpload()))  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 500
        assert "RuntimeError" in exc.detail
    else:
        raise AssertionError("Expected an HTTPException")
