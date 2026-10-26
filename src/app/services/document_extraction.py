from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.repositories.sql_documents import SQLDocumentRepository
from app.schemas.extraction import DocumentExtractionResponse
from app.services.scaneame import (
    ScaneameAPIError,
    ScaneameConfigurationError,
    ScaneameInputError,
    ScaneameProcessingTimeout,
    ScaneameProtocolError,
    extract_ticket,
)

logger = logging.getLogger(__name__)

# Límite por archivo: 10 MB cubre fotos de tickets con margen y evita el OOM
# de un contenedor pequeño (el body no tiene límite por defecto en Starlette).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def read_capped_upload(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Lee un upload aplicando el límite de tamaño antes y mientras se bufferiza.

    Rechaza con 413 por el tamaño declarado (UploadFile.size) sin leer nada y,
    si el tamaño declarado miente, corta la lectura en cuanto se supera el tope.
    """
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=_size_error_detail())
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=_size_error_detail())
        chunks.append(chunk)
    return b"".join(chunks)


def _size_error_detail() -> str:
    return f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB por documento."


class DocumentExtractionService:
    """Coordinates Scanéame extraction and SQL persistence for uploaded documents."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def extract_and_store(
        self,
        file: UploadFile,
    ) -> DocumentExtractionResponse:
        """Extract structured data from a file and store the result."""

        document_name = file.filename or "uploaded_file"
        content_type = (file.content_type or "application/octet-stream").lower()
        mime_type = content_type.split(";", maxsplit=1)[0].strip()
        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Formato no soportado: {content_type}. Usa una imagen o un PDF.",
            )
        document_bytes = await read_capped_upload(file)
        if not document_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El archivo está vacío.",
            )

        repo = SQLDocumentRepository(self._session)

        try:
            extracted_structure = await extract_ticket(document_bytes, content_type)
        except HTTPException:
            raise
        except ScaneameConfigurationError as exc:
            logger.error("Scanéame is not configured")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SCANEAME_API_KEY no está configurada.") from exc
        except ScaneameInputError as exc:
            logger.warning("Invalid Scanéame input for %s: %s", document_name, exc)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        except ScaneameProcessingTimeout as exc:
            logger.error("Scanéame processing timeout for %s", document_name)
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Scanéame tardó demasiado en procesar el documento.") from exc
        except ScaneameAPIError as exc:
            logger.error("Scanéame API error for %s (HTTP %s): %s", document_name, exc.status_code, exc.detail)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de Scanéame: {exc.detail}") from exc
        except ScaneameProtocolError as exc:
            logger.warning("Invalid Scanéame response for %s: %s", document_name, exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Scanéame devolvió una respuesta no válida.") from exc
        except Exception as exc:
            logger.exception("Unexpected extraction error for %s", document_name)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno ({type(exc).__name__}).") from exc

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
                    "Scanéame no pudo extraer estos campos obligatorios: "
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
