import asyncio
import base64
import json

import httpx
import pytest

from app.services.scaneame import (
    ScaneameAPIError,
    ScaneameClient,
    _validate_ticket_result,
)

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
    image = b"\x89PNG\r\n"

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
        _client(httpx.MockTransport(handler)).process_document(b"image", "image/jpeg")
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
        asyncio.run(_client(transport).process_document(b"image", "image/jpeg"))

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
