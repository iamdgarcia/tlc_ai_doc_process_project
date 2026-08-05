from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.extraction import (
    StructuredExtraction,
    SupermercadoExtraction,
    ProductoCantidadExtraction,
)


client = TestClient(app)


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

    def fake_llm_as_structured_output(**_: object) -> StructuredExtraction:
        return mocked_output

    def fake_save(self, extraction: StructuredExtraction) -> int:
        return len(extraction.productos)

    monkeypatch.setattr(
        "app.services.document_extraction.llm_as_structured_output",
        fake_llm_as_structured_output,
    )
    monkeypatch.setattr(
        "app.repositories.sql_documents.SQLDocumentRepository.save",
        fake_save,
    )

    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("invoice.pdf", BytesIO(b"dummy pdf bytes"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_name"] == "invoice.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["stored_document_id"] == "T-TEST-001"
    assert body["message"] == "Document processed successfully"
    assert body["extraction"]["supermercado"]["nombre_supermercado"] == "Supermercado Central"
    assert body["extraction"]["dia"] == "2026-07-15"
    assert body["extraction"]["hora"] == "18:45:00"
    assert body["extraction"]["total"] == 154.75
    assert body["extraction"]["productos"][0]["nombre_producto"] == "Naranjas"
    assert body["extraction"]["productos"][0]["cantidad"] == "2kg"
    assert body["extraction"]["productos"][0]["precio"] == 3.5
