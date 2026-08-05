from __future__ import annotations

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.repositories.sql_documents import SQLDocumentRepository
from app.schemas.extraction import DocumentExtractionResponse, StructuredExtraction
from app.services.llm import StructuredLLMInput, llm_as_structured_output


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

        repo = SQLDocumentRepository(self._session)

        supermercados = repo.get_supermercado_list()  # Get the list of known supermarkets

        extracted_structure = llm_as_structured_output(
            payload=StructuredLLMInput(
                document_name=file.filename or "uploaded_file",
                content_type=file.content_type or "application/octet-stream",
                document_bytes=document_bytes,
                lista_supermercados=supermercados  # Pass the list of known supermarkets
            ),
            response_model=StructuredExtraction,
        )

        if not extracted_structure.id_ticket:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No se pudo extraer el id_ticket del documento. El ticket no tiene número visible.",
            )

        repo.save(extracted_structure)

        return DocumentExtractionResponse(
            document_name=file.filename or "uploaded_file",
            content_type=file.content_type or "application/octet-stream",
            stored_document_id=extracted_structure.id_ticket,
            message="Document processed successfully",
            extraction=extracted_structure,
        )
