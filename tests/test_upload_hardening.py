"""Upload hardening: size cap (413) and content-type allowlist (415)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.document_extraction import (
    MAX_UPLOAD_BYTES,
    DocumentExtractionService,
)


class FakeUpload:
    """UploadFile stand-in with Starlette's read(size) semantics."""

    def __init__(self, data: bytes, content_type: str = "image/jpeg", size: int | None = None) -> None:
        self.filename = "ticket.jpg"
        self.content_type = content_type
        self._data = data
        self._cursor = 0
        self.size = size if size is not None else len(data)

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            self._cursor = len(self._data)
            return self._data
        chunk = self._data[self._cursor : self._cursor + size]
        self._cursor += len(chunk)
        return chunk


def _reject_oversized(upload: FakeUpload, monkeypatch) -> HTTPException:
    calls: list[object] = []

    async def fake_extract(*_: object) -> None:
        calls.append(object())

    monkeypatch.setattr("app.services.document_extraction.extract_ticket", fake_extract)
    service = DocumentExtractionService(session=object())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.extract_and_store(upload))
    assert not calls  # el proveedor nunca recibe la llamada
    return caught.value


def test_oversized_declared_size_rejects_with_413_before_reading(monkeypatch) -> None:
    read_calls: list[int] = []

    class LyingSizeUpload(FakeUpload):
        async def read(self, size: int = -1) -> bytes:
            read_calls.append(size)
            return await super().read(size)

    upload = LyingSizeUpload(b"", size=MAX_UPLOAD_BYTES + 1)
    exc = _reject_oversized(upload, monkeypatch)

    assert exc.status_code == 413
    assert not read_calls  # no se lee ni un byte


def test_lying_declared_size_is_caught_by_the_capped_read(monkeypatch) -> None:
    upload = FakeUpload(b"x" * (MAX_UPLOAD_BYTES + 1), size=1)
    exc = _reject_oversized(upload, monkeypatch)

    assert exc.status_code == 413


def test_rejected_oversized_pdf_uses_the_same_cap(monkeypatch) -> None:
    upload = FakeUpload(b"x" * (MAX_UPLOAD_BYTES + 1), content_type="application/pdf")
    exc = _reject_oversized(upload, monkeypatch)

    assert exc.status_code == 413


def test_disallowed_content_type_rejects_with_415(monkeypatch) -> None:
    upload = FakeUpload(b"hello", content_type="text/plain")

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            DocumentExtractionService(session=object()).extract_and_store(upload)  # type: ignore[arg-type]
        )

    assert caught.value.status_code == 415


def test_extract_endpoint_returns_413_and_415_over_http(api_client) -> None:
    with patch("app.main.MASTER_KEY", "test-master-key"):
        headers = {"Authorization": "Bearer test-master-key"}

        oversized = api_client.post(
            "/api/v1/documents/extract",
            files={"file": ("big.jpg", b"0" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")},
            headers=headers,
        )
        wrong_type = api_client.post(
            "/api/v1/documents/extract",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=headers,
        )

    assert oversized.status_code == 413
    assert wrong_type.status_code == 415
