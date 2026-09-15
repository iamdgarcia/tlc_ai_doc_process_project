from __future__ import annotations

import json
import logging

from fastapi import HTTPException, UploadFile, status
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.sql_documents import SQLDocumentRepository
from app.schemas.extraction import DocumentExtractionResponse, StructuredExtraction
from app.services.llm import StructuredLLMInput, llm_as_structured_output

logger = logging.getLogger(__name__)


def _provider_error_detail(error: APIStatusError) -> str:
    """Return a short provider error without leaking request contents."""

    message = getattr(error, "message", "") or str(error)
    return " ".join(message.split())[:300]


class DocumentExtractionService:
    """Coordinates LLM-based extraction and SQL persistence for uploaded documents."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def extract_and_store(
        self,
        file: UploadFile,
    ) -> DocumentExtractionResponse:
        """Extract structured data from a file and store the result."""

        document_bytes = await file.read()
        document_name = file.filename or "uploaded_file"
        content_type = (file.content_type or "application/octet-stream").lower()
        if not document_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El archivo está vacío.",
            )
        if not (content_type.startswith("image/") or content_type == "application/pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Formato no soportado: {content_type}. Usa una imagen o un PDF.",
            )

        repo = SQLDocumentRepository(self._session)

        supermercados = repo.get_supermercado_list()  # Get the list of known supermarkets

        try:
            extracted_structure = llm_as_structured_output(
                payload=StructuredLLMInput(
                    document_name=document_name,
                    content_type=content_type,
                    document_bytes=document_bytes,
                    lista_supermercados=supermercados,
                ),
                response_model=StructuredExtraction,
            )
        except HTTPException:
            raise
        except AuthenticationError as exc:
            logger.warning("LLM authentication failed for %s", document_name)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="El proveedor de IA rechazó la API key configurada.",
            ) from exc
        except NotFoundError as exc:
            logger.warning("LLM model not found for %s: %s", document_name, settings.openai_model)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"El modelo '{settings.openai_model}' no está disponible en el proveedor "
                    "configurado. Revisa OPENAI_MODEL y BASE_URL."
                ),
            ) from exc
        except RateLimitError as exc:
            logger.warning("LLM rate limit while processing %s", document_name)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El proveedor de IA ha alcanzado su límite de peticiones. Inténtalo más tarde.",
            ) from exc
        except APITimeoutError as exc:
            logger.warning("LLM timeout while processing %s", document_name)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="El proveedor de IA tardó demasiado en responder.",
            ) from exc
        except APIConnectionError as exc:
            logger.warning("LLM connection error while processing %s: %s", document_name, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo conectar con el proveedor de IA. Revisa BASE_URL y la red.",
            ) from exc
        except BadRequestError as exc:
            detail = _provider_error_detail(exc)
            logger.warning("LLM rejected %s: %s", document_name, detail)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"El proveedor rechazó el documento o el modelo: {detail}",
            ) from exc
        except APIStatusError as exc:
            detail = _provider_error_detail(exc)
            logger.warning("LLM provider error for %s: %s", document_name, detail)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error del proveedor de IA: {detail}",
            ) from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Invalid structured response for %s: %s", document_name, exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El modelo no devolvió una estructura de ticket válida.",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected extraction error for %s", document_name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error interno de extracción ({type(exc).__name__}). Consulta el log del servidor.",
            ) from exc

        missing_fields = []
        if not extracted_structure.id_ticket:
            missing_fields.append("id_ticket")
        if not extracted_structure.supermercado.nombre_supermercado:
            missing_fields.append("supermercado")
        if not extracted_structure.dia:
            missing_fields.append("dia")
        if not extracted_structure.hora:
            missing_fields.append("hora")
        if not extracted_structure.productos:
            missing_fields.append("productos")
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "El modelo no pudo extraer estos campos obligatorios: "
                    f"{', '.join(missing_fields)}. Comprueba la calidad de la imagen."
                ),
            )

        try:
            repo.save(extracted_structure)
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid extracted values for %s: %s", document_name, exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Los datos extraídos no son válidos: {exc}",
            ) from exc
        except Exception as exc:
            logger.exception("Could not store extracted ticket from %s", document_name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="El ticket se extrajo, pero no se pudo guardar en la base de datos.",
            ) from exc

        return DocumentExtractionResponse(
            document_name=document_name,
            content_type=content_type,
            stored_document_id=extracted_structure.id_ticket,
            message="Document processed successfully",
            extraction=extracted_structure,
        )
