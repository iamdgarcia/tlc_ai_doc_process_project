import asyncio
from io import BytesIO

from fastapi import HTTPException, Response, UploadFile

from app.api.v1.extraction import extract_documents
from app.schemas.extraction import (
    DocumentExtractionResponse,
    StructuredExtraction,
    SupermercadoExtraction,
)
from app.services.document_extraction import DocumentExtractionService


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
    result = asyncio.run(extract_documents(files=files, session=None, response=response))

    assert result.total == 2
    assert result.successful == 1
    assert result.failed == 1
    assert result.results[0].document_name == "ok.pdf"
    assert result.errors[0].document_name == "bad.pdf"
    assert result.errors[0].error == "Ticket ilegible"
    assert response.status_code == 207


def test_extraction_exposes_safe_unexpected_error(monkeypatch) -> None:
    class MemoryUpload:
        filename = "ticket.jpg"
        content_type = "image/jpeg"

        async def read(self) -> bytes:
            return b"image"

    def broken_extraction(**_):
        raise RuntimeError("provider response was invalid")

    monkeypatch.setattr(
        "app.services.document_extraction.llm_as_structured_output",
        broken_extraction,
    )
    service = DocumentExtractionService(session=object())
    monkeypatch.setattr(
        "app.services.document_extraction.SQLDocumentRepository.get_supermercado_list",
        lambda self: [],
    )
    try:
        asyncio.run(service.extract_and_store(MemoryUpload()))  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 500
        assert "RuntimeError" in exc.detail
    else:
        raise AssertionError("Expected an HTTPException")
