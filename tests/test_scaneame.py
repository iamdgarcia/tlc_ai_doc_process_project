import asyncio
import base64
import io
import json

import httpx
import pytest
from PIL import Image

from app.services.scaneame import (
    ScaneameAPIError,
    ScaneameClient,
    ScaneameInputError,
    ScaneameProcessingTimeout,
    _document_input,
    _validate_ticket_result,
)


def _png_bytes() -> bytes:
    """Un PNG real de 8x8: el cliente ahora valida la cabecera de la imagen."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    return buffer.getvalue()

EXTRACTION = {
    "id_ticket": "T-SCANEAME-1",
    "supermercado": {"nombre_supermercado": "mercadona"},
    "dia": "2026-09-30",
    "hora": "19:42",
    "total": 12.5,
    "productos": [
        {"nombre_producto": "pan", "cantidad": "1", "precio": 1.25},
    ],
}


def _client(transport: httpx.AsyncBaseTransport) -> ScaneameClient:
    return ScaneameClient(
        api_key="test-api-key",
        api_url="https://scaneame.example/v1/process",
        endpoint="tickets",
        request_timeout_seconds=5,
        processing_timeout_seconds=5,
        poll_interval_seconds=0,
        transport=transport,
    )


def test_process_document_sends_image_data_url_and_returns_sync_result() -> None:
    image = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "https://scaneame.example/v1/process"
        assert request.headers["Authorization"] == "Bearer test-api-key"
        payload = json.loads(request.content)
        assert payload == {
            "endpoint": "tickets",
            "input": f"data:image/png;base64,{base64.b64encode(image).decode('ascii')}",
        }
        return httpx.Response(200, json={"status": "ok", "result": EXTRACTION})

    result = asyncio.run(
        _client(httpx.MockTransport(handler)).process_document(image, "image/png")
    )

    assert result == EXTRACTION


def test_process_document_polls_an_async_job_until_done() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.method == "POST":
            return httpx.Response(200, json={"status": "async", "job_id": "job-123"})
        if requests.count("GET /v1/jobs/job-123") == 1:
            return httpx.Response(200, json={"status": "processing"})
        return httpx.Response(
            200,
            json={"status": "done", "result": {"result": EXTRACTION, "usage": {}}},
        )

    result = asyncio.run(
        _client(httpx.MockTransport(handler)).process_document(_png_bytes(), "image/png")
    )

    assert result == EXTRACTION
    assert requests == [
        "POST /v1/process",
        "GET /v1/jobs/job-123",
        "GET /v1/jobs/job-123",
    ]


def test_process_document_exposes_safe_api_error_message() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            401,
            json={"error": "UNAUTHORIZED", "message": "Clave API no válida o revocada"},
        )
    )

    with pytest.raises(ScaneameAPIError) as caught:
        asyncio.run(
            _client(transport).process_document(_png_bytes(), "image/png")
        )

    assert caught.value.status_code == 401
    assert caught.value.detail == "Clave API no válida o revocada"


def test_scaneame_ticket_result_is_adapted_to_the_internal_schema() -> None:
    result = _validate_ticket_result(
        {
            "id_ticket": "3142-010-217943",
            "productos": [
                {
                    "cantidad": "2",
                    "producto": "ÑOQUIS DE PATATA",
                    "importe_linea": 2.0,
                    "precio_unitario": 1.0,
                },
                {
                    "cantidad": "0,428 kg",
                    "producto": "TOMATE CANARIO",
                    "importe_linea": 0.86,
                    "precio_unitario": 2.0,
                },
            ],
            "hora_compra": "17:06",
            "fecha_compra": "2026-02-20",
            "supermercado": "MERCADONA, S.A.",
            "total_compra": 88.07,
        }
    )

    assert result.id_ticket == "3142-010-217943"
    assert result.supermercado.nombre_supermercado == "MERCADONA, S.A."
    assert result.dia == "2026-02-20"
    assert result.hora == "17:06"
    assert result.total == 88.07
    assert result.productos[0].nombre_producto == "ÑOQUIS DE PATATA"
    assert result.productos[0].cantidad == "2"
    assert result.productos[0].precio == 1.0
    assert result.productos[1].cantidad == "0,428 kg"
    assert result.productos[1].precio == 2.0


def test_poll_survives_one_transient_error_and_completes() -> None:
    polls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"status": "async", "job_id": "job-9"})
        polls["count"] += 1
        if polls["count"] == 1:
            return httpx.Response(503, json={"message": "upstream saturado"})
        if polls["count"] == 2:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(
            200,
            json={"status": "done", "result": {"result": EXTRACTION}},
        )

    result = asyncio.run(
        _client(httpx.MockTransport(handler)).process_document(_png_bytes(), "image/png")
    )

    assert result == EXTRACTION
    assert polls["count"] == 3


def test_poll_aborts_on_definitive_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"status": "async", "job_id": "job-404"})
        return httpx.Response(404, json={"message": "job inexistente"})

    with pytest.raises(ScaneameAPIError) as caught:
        asyncio.run(
            _client(httpx.MockTransport(handler)).process_document(_png_bytes(), "image/png")
        )

    assert caught.value.status_code == 404


def test_processing_timeout_raises_when_job_never_finishes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"status": "async", "job_id": "job-never"})
        return httpx.Response(200, json={"status": "processing"})

    client = ScaneameClient(
        api_key="test-api-key",
        api_url="https://scaneame.example/v1/process",
        endpoint="tickets",
        request_timeout_seconds=5,
        processing_timeout_seconds=0.05,
        poll_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ScaneameProcessingTimeout):
        asyncio.run(client.process_document(_png_bytes(), "image/png"))


def test_jobs_url_preserves_the_base_path_prefix() -> None:
    client = ScaneameClient(
        api_key="test-api-key",
        api_url="https://scaneame.example/api/v1/process",
        endpoint="tickets",
        request_timeout_seconds=5,
        processing_timeout_seconds=5,
        poll_interval_seconds=0,
    )

    assert str(client._jobs_url("job-7")) == "https://scaneame.example/api/v1/jobs/job-7"


def test_async_job_is_polled_at_the_base_path_aware_url() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(200, json={"status": "async", "job_id": "job-7"})
        return httpx.Response(
            200, json={"status": "done", "result": {"result": EXTRACTION}}
        )

    client = ScaneameClient(
        api_key="test-api-key",
        api_url="https://scaneame.example/api/v1/process",
        endpoint="tickets",
        request_timeout_seconds=5,
        processing_timeout_seconds=5,
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.process_document(_png_bytes(), "image/png"))

    assert result == EXTRACTION
    assert seen_paths == ["/api/v1/process", "/api/v1/jobs/job-7"]


def test_oversized_image_is_rejected_as_input_error(monkeypatch) -> None:
    # 2500 px > 2 * 100: PIL lanza DecompressionBombError en Image.open
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    big_px = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(big_px, format="PNG")

    with pytest.raises(ScaneameInputError, match="demasiado grande"):
        _document_input(big_px.getvalue(), "image/png")


def test_invalid_image_bytes_are_rejected_as_input_error() -> None:
    with pytest.raises(ScaneameInputError, match="no es una imagen válida"):
        _document_input(b"definitely not an image", "image/jpeg")


def test_module_pins_an_explicit_decompression_bomb_limit() -> None:
    from app.services import scaneame

    assert Image.MAX_IMAGE_PIXELS == scaneame._MAX_IMAGE_PIXELS == 50_000_000
