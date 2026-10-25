from __future__ import annotations

import asyncio
import base64
import io
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from app.core.config import settings
from app.schemas.extraction import (
    ProductoCantidadExtraction,
    StructuredExtraction,
    SupermercadoExtraction,
)


class ScaneameError(Exception):
    """Base error raised by the Scanéame integration."""


class ScaneameConfigurationError(ScaneameError):
    """The Scanéame client is not configured."""


class ScaneameInputError(ScaneameError):
    """The uploaded document cannot be represented as a Scanéame input."""


class ScaneameProtocolError(ScaneameError):
    """Scanéame returned a response that does not follow its API contract."""


class ScaneameProcessingTimeout(ScaneameError):
    """An asynchronous Scanéame job did not finish before the deadline."""


class ScaneameAPIError(ScaneameError):
    """Scanéame rejected a request or failed while processing it."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ScaneameProductResult(BaseModel):
    """Product row returned by the deployed Scanéame `tickets` endpoint."""

    cantidad: str | float | int
    producto: str
    importe_linea: float
    precio_unitario: float | None = None


class ScaneameTicketResult(BaseModel):
    """Public result contract of the deployed Scanéame `tickets` endpoint."""

    id_ticket: str
    productos: list[ScaneameProductResult]
    hora_compra: str
    fecha_compra: str
    supermercado: str
    total_compra: float


_MAX_IMAGE_BYTES = 1_500_000  # ~1.5 MB antes de base64 (base64 añade ~33%)
_MAX_IMAGE_PX = 1920

# ponytail: PIL acepta ~178Mpx por defecto (~500MB RGB). Límite explícito;
# PIL lanza DecompressionBombError por encima del doble de este valor.
_MAX_IMAGE_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS


def _open_image(data: bytes) -> Image.Image:
    """Abre una imagen validando cabecera; los bytes basura/inválidos son 4xx, no 500."""
    try:
        return Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ScaneameInputError(
            "La imagen es demasiado grande para procesarse."
        ) from exc
    except Exception as exc:
        raise ScaneameInputError("El archivo no es una imagen válida.") from exc


def _compress_image(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Reduce imagen a ≤_MAX_IMAGE_BYTES reescalando y recomprimiendo a JPEG."""
    img = _open_image(data)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Reescalar si algún lado supera el límite
    w, h = img.size
    if max(w, h) > _MAX_IMAGE_PX:
        scale = _MAX_IMAGE_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Comprimir con calidad decreciente hasta entrar en el límite
    for quality in (85, 70, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _MAX_IMAGE_BYTES:
            return compressed, "image/jpeg"

    return compressed, "image/jpeg"  # mejor esfuerzo


def _document_input(document_bytes: bytes, content_type: str) -> str:
    """Build the value accepted by Scanéame's `input` field."""

    mime_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if mime_type.startswith("image/"):
        # Valida la cabecera antes de codificar/gastar bytes: un content-type
        # mentiroso no debe llegar al proveedor como base64 de basura.
        with _open_image(document_bytes) as probe:
            probe.verify()
        if len(document_bytes) > _MAX_IMAGE_BYTES:
            document_bytes, mime_type = _compress_image(document_bytes, mime_type)
        encoded_document = base64.b64encode(document_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded_document}"

    if mime_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(document_bytes))
            extracted_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
        except Exception as exc:
            raise ScaneameInputError("No se pudo leer el archivo PDF.") from exc
        if not extracted_text:
            raise ScaneameInputError(
                "El PDF no contiene texto extraíble. Convierte sus páginas a imagen antes de subirlo."
            )
        return extracted_text

    raise ScaneameInputError(f"Formato no soportado por Scanéame: {mime_type}.")


def _error_detail(payload: object, fallback: str) -> str:
    if isinstance(payload, dict):
        message = (
            payload.get("message") or payload.get("detail") or payload.get("error")
        )
        if isinstance(message, str) and message.strip():
            return " ".join(message.split())[:300]
    return fallback


def _validate_ticket_result(raw_result: object) -> StructuredExtraction:
    """Convert Scanéame's public ticket schema into the application's domain schema."""

    try:
        return StructuredExtraction.model_validate(raw_result)
    except ValidationError:
        pass

    try:
        ticket = ScaneameTicketResult.model_validate(raw_result)
    except ValidationError as exc:
        raise ScaneameProtocolError(
            "El resultado de Scanéame no cumple la estructura esperada para un ticket."
        ) from exc

    return StructuredExtraction(
        id_ticket=ticket.id_ticket,
        supermercado=SupermercadoExtraction(
            nombre_supermercado=ticket.supermercado,
        ),
        dia=ticket.fecha_compra,
        hora=ticket.hora_compra,
        total=ticket.total_compra,
        productos=[
            ProductoCantidadExtraction(
                nombre_producto=product.producto,
                cantidad=product.cantidad,
                precio=(
                    product.precio_unitario
                    if product.precio_unitario is not None
                    else product.importe_linea
                ),
            )
            for product in ticket.productos
        ],
    )


class ScaneameClient:
    """HTTP client for the Scanéame processing and job APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        endpoint: str,
        request_timeout_seconds: float,
        processing_timeout_seconds: float,
        poll_interval_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._endpoint = endpoint
        self._request_timeout_seconds = request_timeout_seconds
        self._processing_timeout_seconds = processing_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._transport = transport

    async def process_document(
        self, document_bytes: bytes, content_type: str
    ) -> object:
        input_value = _document_input(document_bytes, content_type)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self._request_timeout_seconds)
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            transport=self._transport,
        ) as client:
            response = await client.post(
                self._api_url,
                json={"endpoint": self._endpoint, "input": input_value},
            )
            body = self._parse_response(response)
            response_status = body.get("status")
            if response_status == "ok":
                if "result" not in body:
                    raise ScaneameProtocolError(
                        "Scanéame no devolvió el resultado de extracción."
                    )
                return body["result"]
            if response_status == "async":
                job_id = body.get("job_id")
                if not isinstance(job_id, str) or not job_id:
                    raise ScaneameProtocolError(
                        "Scanéame no devolvió un identificador de trabajo."
                    )
                return await self._wait_for_job(client, job_id)
            raise ScaneameProtocolError(
                f"Estado de procesamiento de Scanéame no reconocido: {response_status!r}."
            )

    def _jobs_url(self, job_id: str) -> httpx.URL:
        """Jobs endpoint como hermano de la ruta de proceso: preserva el base path.

        `URL.join('/v1/jobs/...')` descartaba cualquier prefijo del api_url
        (p. ej. https://host/api/v1/process → https://host/v1/jobs/... = 404).
        """
        process_url = httpx.URL(self._api_url)
        parent = process_url.path.rstrip("/").rsplit("/", 1)[0]
        return process_url.copy_with(path=f"{parent}/jobs/{quote(job_id, safe='')}")

    async def _wait_for_job(self, client: httpx.AsyncClient, job_id: str) -> object:
        deadline = monotonic() + self._processing_timeout_seconds
        job_url = self._jobs_url(job_id)

        while monotonic() < deadline:
            try:
                response = await client.get(job_url)
                body = self._parse_response(response)
            except httpx.HTTPError:
                body = None  # error de transporte transitorio: se reintenta hasta el deadline
            except ScaneameAPIError as exc:
                if exc.status_code < 500:
                    raise  # 4xx = error definitivo de la API
                body = None  # 5xx transitorio
            if body is None:
                await self._sleep_between_polls(deadline)
                continue
            job_status = body.get("status")
            if job_status in {"queued", "processing"}:
                await self._sleep_between_polls(deadline)
                continue
            if job_status == "failed":
                detail = _error_detail(
                    body,
                    "Scanéame no pudo procesar el documento.",
                )
                raise ScaneameAPIError(status_code=502, detail=detail)
            if job_status == "done":
                result_wrapper = body.get("result")
                if (
                    not isinstance(result_wrapper, dict)
                    or "result" not in result_wrapper
                ):
                    raise ScaneameProtocolError(
                        "Scanéame devolvió un trabajo completado sin resultado de extracción."
                    )
                return result_wrapper["result"]
            raise ScaneameProtocolError(
                f"Estado de trabajo de Scanéame no reconocido: {job_status!r}."
            )

        raise ScaneameProcessingTimeout(
            "Scanéame no terminó de procesar el documento dentro del tiempo permitido."
        )

    async def _sleep_between_polls(self, deadline: float) -> None:
        remaining = deadline - monotonic()
        if self._poll_interval_seconds <= 0 or remaining <= 0:
            return
        # ponytail: backoff exponencial simple (cap 8s), reduce la carga en jobs atascados
        polls_so_far = int((self._processing_timeout_seconds - remaining) / max(self._poll_interval_seconds, 1))
        backoff = min(self._poll_interval_seconds * (2 ** min(polls_so_far, 3)), 8.0)
        await asyncio.sleep(min(backoff, remaining))

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ScaneameProtocolError(
                "Scanéame devolvió una respuesta que no es JSON."
            ) from exc

        if not isinstance(body, dict):
            raise ScaneameProtocolError(
                "Scanéame devolvió una respuesta JSON no válida."
            )
        if response.is_error:
            raise ScaneameAPIError(
                status_code=response.status_code,
                detail=_error_detail(
                    body, f"Scanéame devolvió el error HTTP {response.status_code}."
                ),
            )
        return body


async def extract_ticket(
    document_bytes: bytes, content_type: str
) -> StructuredExtraction:
    """Extract and validate one ticket through the configured Scanéame endpoint."""

    if not settings.scaneame_api_key:
        raise ScaneameConfigurationError("SCANEAME_API_KEY is not configured")

    client = ScaneameClient(
        api_key=settings.scaneame_api_key,
        api_url=settings.scaneame_api_url,
        endpoint=settings.scaneame_endpoint,
        request_timeout_seconds=settings.scaneame_request_timeout_seconds,
        processing_timeout_seconds=settings.scaneame_processing_timeout_seconds,
        poll_interval_seconds=settings.scaneame_poll_interval_seconds,
    )
    raw_result = await client.process_document(document_bytes, content_type)
    return _validate_ticket_result(raw_result)
