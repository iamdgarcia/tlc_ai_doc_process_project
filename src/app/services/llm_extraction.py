"""Two-step ticket extraction: OCR via deepseek-ocr-2, then JSON parse via a cheap fast model.

Replaces the Scaneame dependency entirely.
Step 1 — image → raw text (deepseek-ocr-2, specialized OCR model)
Step 2 — raw text → StructuredExtraction (cheap chat model, JSON mode)
PDFs skip step 1; pypdf extracts the text directly.
"""
from __future__ import annotations

import base64
import io
import json
import logging

import openai
from pydantic import ValidationError
from pypdf import PdfReader

from app.core.config import settings
from app.schemas.extraction import (
    ProductoCantidadExtraction,
    StructuredExtraction,
    SupermercadoExtraction,
)

logger = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 1_500_000  # ~1.5 MB before base64 (~33% overhead)
_MAX_IMAGE_PX = 1920

_EXTRACT_PROMPT = """\
Eres un extractor de datos de tickets de compra. A partir del texto OCR a continuación, \
devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta (sin texto adicional):

{
  "id_ticket": "<id o null>",
  "supermercado": {"nombre_supermercado": "<nombre o null>"},
  "dia": "<YYYY-MM-DD o null>",
  "hora": "<HH:MM o null>",
  "total": <número o null>,
  "productos": [
    {"nombre_producto": "<nombre>", "cantidad": "<cantidad con unidad o número>", "precio": <float o null>}
  ]
}

TEXTO OCR DEL TICKET:
{text}"""


def _client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        base_url=settings.openai_base_url or "https://api.novita.ai/openai",
        api_key=settings.openai_api_key or "",
    )


def _compress_image(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Shrink image to ≤_MAX_IMAGE_BYTES before sending to the OCR model."""
    from PIL import Image  # lazy — only used for large images

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > _MAX_IMAGE_PX:
        scale = _MAX_IMAGE_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    for quality in (85, 70, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _MAX_IMAGE_BYTES:
            return compressed, "image/jpeg"
    return compressed, "image/jpeg"  # best effort


async def _ocr_image(document_bytes: bytes, mime_type: str) -> str:
    """Step 1: send the image to deepseek-ocr-2 and return raw OCR text."""
    if len(document_bytes) > _MAX_IMAGE_BYTES:
        document_bytes, mime_type = _compress_image(document_bytes, mime_type)

    data_url = f"data:{mime_type};base64,{base64.b64encode(document_bytes).decode()}"
    client = _client()
    response = await client.chat.completions.create(
        model=settings.ocr_model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "<|grounding|>OCR this image."},
            ],
        }],
        max_tokens=4096,
    )
    text = (response.choices[0].message.content or "").strip()
    logger.debug("OCR output (%d chars): %.200s", len(text), text)
    return text


def _pdf_text(document_bytes: bytes) -> str:
    """Extract plain text from a PDF using pypdf."""
    reader = PdfReader(io.BytesIO(document_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError(
            "El PDF no contiene texto extraíble. Convierte sus páginas a imagen antes de subirlo."
        )
    return text


async def _parse_to_schema(text: str) -> StructuredExtraction:
    """Step 2: cheap model maps OCR text → StructuredExtraction via JSON mode."""
    client = _client()
    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.replace("{text}", text)}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1024,
    )
    raw = (response.choices[0].message.content or "{}").strip()
    logger.debug("Extraction raw response: %.500s", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"El modelo devolvió JSON inválido: {exc}") from exc
    try:
        return StructuredExtraction.model_validate(data)
    except ValidationError as exc:
        # Empty dict = the model couldn't extract anything (bad image, unreadable OCR, refusal)
        if not data:
            raise ValueError(
                "El modelo no pudo extraer datos del ticket. "
                "Comprueba que la imagen sea legible y contenga un ticket de compra."
            ) from exc
        logger.warning("Extraction schema mismatch. data=%r error=%s", data, exc)
        raise ValueError(f"Los datos extraídos no cumplen el esquema: {exc}") from exc


async def extract_ticket(document_bytes: bytes, content_type: str) -> StructuredExtraction:
    """Extract a StructuredExtraction from an image or PDF.

    Images  → OCR (deepseek-ocr-2) → structured parse (openai_chat_model)
    PDFs    → pypdf text extract   → structured parse (openai_chat_model)
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")

    mime_type = content_type.split(";", maxsplit=1)[0].strip().lower()

    if mime_type.startswith("image/"):
        text = await _ocr_image(document_bytes, mime_type)
    elif mime_type == "application/pdf":
        text = _pdf_text(document_bytes)
    else:
        raise ValueError(f"Formato no soportado: {mime_type}.")

    if not text:
        raise ValueError("No se pudo extraer texto del documento.")

    return await _parse_to_schema(text)
