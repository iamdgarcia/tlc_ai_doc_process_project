import asyncio

from app.schemas.extraction import (
    ProductoCantidadExtraction,
    StructuredExtraction,
    SupermercadoExtraction,
)
from app.services.document_extraction import DocumentExtractionService


def test_extract_document_returns_structured_response(monkeypatch) -> None:
    mocked_output = StructuredExtraction(
        id_ticket="T-TEST-001",
        supermercado=SupermercadoExtraction(
            nombre_supermercado="Supermercado Central",
        ),
        dia="2026-07-15",
        hora="18:45:00",
        total=154.75,
        productos=[
            ProductoCantidadExtraction(
                nombre_producto="Naranjas",
                cantidad="2kg",
                precio=3.5,
            )
        ],
    )

    async def fake_extract_ticket(*_: object) -> StructuredExtraction:
        return mocked_output

    def fake_save(self, extraction: StructuredExtraction) -> int:
        return len(extraction.productos)

    monkeypatch.setattr(
        "app.services.document_extraction.extract_ticket",
        fake_extract_ticket,
    )
    monkeypatch.setattr(
        "app.repositories.sql_documents.SQLDocumentRepository.save",
        fake_save,
    )

    class MemoryUpload:
        filename = "invoice.pdf"
        content_type = "application/pdf"

        async def read(self) -> bytes:
            return b"dummy pdf bytes"

    upload = MemoryUpload()
    response = asyncio.run(
        DocumentExtractionService(session=object()).extract_and_store(upload)  # type: ignore[arg-type]
    )

    body = response.model_dump()
    assert body["document_name"] == "invoice.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["stored_document_id"] == "T-TEST-001"
    assert body["message"] == "Document processed successfully"
    assert (
        body["extraction"]["supermercado"]["nombre_supermercado"]
        == "Supermercado Central"
    )
    assert body["extraction"]["dia"] == "2026-07-15"
    assert body["extraction"]["hora"] == "18:45:00"
    assert body["extraction"]["total"] == 154.75
    assert body["extraction"]["productos"][0]["nombre_producto"] == "Naranjas"
    assert body["extraction"]["productos"][0]["cantidad"] == "2kg"
    assert body["extraction"]["productos"][0]["precio"] == 3.5
