"""Tests for the two-step OCR+extract pipeline (llm_extraction.py)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_extraction import _parse_to_schema, extract_ticket
from app.schemas.extraction import StructuredExtraction


def _mock_completion(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


VALID_JSON = json.dumps({
    "id_ticket": "T001",
    "supermercado": {"nombre_supermercado": "Mercadona"},
    "dia": "2026-01-15",
    "hora": "10:30",
    "total": 42.50,
    "productos": [{"nombre_producto": "Leche", "cantidad": "2", "precio": 1.20}],
})


def test_parse_to_schema_returns_structured_extraction(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion(VALID_JSON))
    monkeypatch.setattr("app.services.llm_extraction._client", lambda: mock_client)

    result = asyncio.run(_parse_to_schema("some OCR text"))

    assert isinstance(result, StructuredExtraction)
    assert result.id_ticket == "T001"
    assert result.supermercado.nombre_supermercado == "Mercadona"
    assert result.total == 42.50
    assert len(result.productos) == 1


def test_parse_to_schema_raises_on_invalid_json(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion("not json"))
    monkeypatch.setattr("app.services.llm_extraction._client", lambda: mock_client)

    with pytest.raises(ValueError, match="JSON"):
        asyncio.run(_parse_to_schema("text"))


def test_extract_ticket_image_calls_ocr_then_parse(monkeypatch):
    """Full pipeline: image → OCR → parse."""
    from app.schemas.extraction import SupermercadoExtraction
    expected = StructuredExtraction(
        id_ticket="T001",
        supermercado=SupermercadoExtraction(nombre_supermercado="Mercadona"),
        dia="2026-01-15", hora="10:30", total=42.50, productos=[],
    )
    monkeypatch.setattr("app.services.llm_extraction._ocr_image",
                        AsyncMock(return_value="TICKET MERCADONA 15/01/2026"))
    monkeypatch.setattr("app.services.llm_extraction._parse_to_schema",
                        AsyncMock(return_value=expected))
    monkeypatch.setattr("app.services.llm_extraction.settings",
                        MagicMock(openai_api_key="sk_test"))

    result = asyncio.run(extract_ticket(b"fake_bytes", "image/jpeg"))
    assert result.id_ticket == "T001"


def test_extract_ticket_pdf_skips_ocr(monkeypatch):
    """PDFs use pypdf, not OCR."""
    ocr_mock = AsyncMock()
    from app.schemas.extraction import SupermercadoExtraction
    parse_mock = AsyncMock(return_value=StructuredExtraction(
        id_ticket="T002", supermercado=SupermercadoExtraction(nombre_supermercado="Carrefour"),
        dia=None, hora=None, total=None, productos=[],
    ))
    monkeypatch.setattr("app.services.llm_extraction._ocr_image", ocr_mock)
    monkeypatch.setattr("app.services.llm_extraction._parse_to_schema", parse_mock)
    monkeypatch.setattr("app.services.llm_extraction._pdf_text", lambda _: "PDF text")
    monkeypatch.setattr("app.services.llm_extraction.settings",
                        MagicMock(openai_api_key="sk_test"))

    asyncio.run(extract_ticket(b"fake_pdf", "application/pdf"))
    ocr_mock.assert_not_called()
    parse_mock.assert_called_once_with("PDF text")


def test_extract_ticket_raises_on_missing_api_key(monkeypatch):
    monkeypatch.setattr("app.services.llm_extraction.settings",
                        MagicMock(openai_api_key=None))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        asyncio.run(extract_ticket(b"bytes", "image/jpeg"))
