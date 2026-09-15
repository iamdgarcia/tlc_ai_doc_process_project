from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from importlib import import_module
from typing import Any, TypeVar

from fastapi import HTTPException, status
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from pydantic import BaseModel, ValidationError

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class StructuredLLMInput:
    """Payload sent to the LLM for structured extraction."""

    document_name: str
    content_type: str
    document_bytes: bytes
    lista_supermercados: list[str]  # List of known supermarket names


_client: Any | None = None
_wrapped_client: Any | None = None


def _get_client() -> Any:
    """Create a reusable OpenAI client when the API key is available."""

    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY is not configured",
            )
        openai_module = import_module("openai")
        _client = openai_module.OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
    return _client


def _get_wrapped_client() -> Any:
    """creates a langsmith client that wraps the openai client to provide a more convenient interface for structured output"""
    global _wrapped_client
    if _wrapped_client is None:
        _wrapped_client = wrap_openai(_get_client())
    return _wrapped_client


def _build_document_context(
    payload: StructuredLLMInput,
    response_model: type[BaseModel],
) -> tuple[str, list[dict[str, Any]]]:
    """Build a prompt and content payload adapted to the input file type."""

    schema = json.dumps(
        response_model.model_json_schema(), ensure_ascii=False, indent=2
    )
    instructions = (
        "Extrae la información estructurada del documento y devuelve SOLO JSON válido "
        "con exactamente los campos definidos en este esquema:\n\n"
        f"{schema}\n\n"
        f"lista de supermercados conocidos: {', '.join(payload.lista_supermercados)}\n\n"
        "Reglas estrictas:\n"
        "- Si un campo no está disponible, usa null.\n"
        "- No incluyas campos que no estén en el esquema.\n"
        "- nombre_producto: solo el nombre del producto en minúsculas, sin cantidades ni unidades "
        "(ej: 'MANDARINAS 2K' → 'mandarinas').\n"
        "- cantidad: extrae la cantidad/unidad separada del nombre "
        "(ej: 'MANDARINAS 2K' → '2kg'; 'K' y 'KG' significan kilogramos).\n"
        "- precio: extrae el precio unitario o de línea del producto tal como aparece en el documento.\n"
        "- id_ticket: extrae el número o código de ticket/recibo tal como aparece en el documento "
        "(ej: número de ticket, referencia de compra). Si no hay número visible, usa null.\n"
        "- dia en formato ISO YYYY-MM-DD, hora en formato HH:MM."
    )

    if payload.content_type.lower().startswith("image/"):
        encoded_document = base64.b64encode(payload.document_bytes).decode("utf-8")
        image_url = f"data:{payload.content_type};base64,{encoded_document}"
        content = [
            {"type": "text", "text": instructions},
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            },
        ]
        return instructions, content

    extracted_text = _extract_pdf_text(payload.document_bytes)
    user_text = (
        f"Documento: {payload.document_name}\n"
        f"Tipo: {payload.content_type}\n\n"
        f"Texto extraído:\n{extracted_text or '[sin texto extraído]'}\n"
    )
    content = [{"type": "text", "text": f"{instructions}\n\n{user_text}"}]
    return instructions, content


def _extract_pdf_text(document_bytes: bytes) -> str:
    """Extract text from a PDF before sending it to the LLM."""

    pypdf_module = import_module("pypdf")
    PdfReader = pypdf_module.PdfReader
    reader = PdfReader(io.BytesIO(document_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


@traceable(name="Extraction Pipeline")
def llm_as_structured_output(
    *,
    payload: StructuredLLMInput,
    response_model: type[T],
) -> T:
    """Call the LLM and coerce the JSON response into a Pydantic model."""
    _, content = _build_document_context(payload, response_model)

    client = _get_wrapped_client()
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Eres un extractor OCR de tickets. Examina la imagen completa y devuelve "
                "todos los campos del esquema. Nunca devuelvas un objeto JSON vacío."
            ),
        },
        {"role": "user", "content": content},
    ]
    last_error: json.JSONDecodeError | ValidationError | None = None
    for attempt in range(2):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content or ""
        try:
            parsed_content = json.loads(raw_content)
            return response_model.model_validate(parsed_content)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if attempt == 0:
                messages.extend(
                    [
                        {"role": "assistant", "content": raw_content or "{}"},
                        {
                            "role": "user",
                            "content": (
                                "La respuesta anterior está vacía o no cumple el esquema. "
                                "Vuelve a examinar el ticket y devuelve el objeto JSON completo, "
                                "incluyendo supermercado y productos."
                            ),
                        },
                    ]
                )

    if last_error is not None:
        raise last_error
    raise ValueError("The model returned no structured response")
