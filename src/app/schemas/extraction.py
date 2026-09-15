from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SupermercadoExtraction(BaseModel):
    """Structured supermarket data for later ID resolution."""

    nombre_supermercado: str | None = Field(default=None)


class ProductoCantidadExtraction(BaseModel):
    """Structured product data with only the fields available at extraction time.

    `cantidad` puede venir como `int`, `float` o `str` (p. ej. "2kg"). Aquí
    aceptamos esos tipos y normalizamos a `str` en validación para evitar
    errores de Pydantic cuando se reciben números.
    """

    nombre_producto: str | None = Field(default=None)
    cantidad: str | float | int | None = Field(
        default=None,
        description="Cantidad, puede incluir unidad, ej. '2kg' o ser numérica",
    )
    precio: float | None = Field(
        default=None, description="Precio por la cantidad indicada, en la moneda del documento"
    )

    @model_validator(mode="after")
    def _coerce_cantidad_to_string(self) -> ProductoCantidadExtraction:
        """Normaliza `cantidad` a `str` cuando es numérica, preservando unidades.

        Ejemplos:
        - 2 -> "2"
        - 0.428 -> "0.428"
        - "2kg" -> "2kg" (sin cambio)
        """

        if self.cantidad is None:
            return self

        if isinstance(self.cantidad, (int, float)):
            # Convertir números a string sin perder precisión innecesaria
            self.cantidad = str(self.cantidad)
        else:
            # Asegurar que cualquier otro tipo se convierta a string
            self.cantidad = str(self.cantidad)

        return self


class StructuredExtraction(BaseModel):
    """Structured payload returned by the LLM."""

    id_ticket: str | None = Field(default=None, description="Número de ticket o referencia del documento")
    supermercado: SupermercadoExtraction
    dia: str | None = Field(default=None, description="Formato ISO YYYY-MM-DD")
    hora: str | None = Field(default=None, description="Formato HH:MM[:SS]")
    total: float | None = Field(default=None)
    productos: list[ProductoCantidadExtraction]


class DocumentExtractionResponse(BaseModel):
    """API response returned after storing the extracted structure."""

    document_name: str = Field(..., examples=["invoice.pdf"])
    content_type: str = Field(..., examples=["application/pdf"])
    stored_document_id: str = Field(..., examples=["T001"])
    message: str = Field(..., examples=["Document processed successfully"])
    extraction: StructuredExtraction


class DocumentExtractionError(BaseModel):
    """Failure for one file in a batch without discarding successful files."""

    document_name: str
    error: str


class BatchDocumentExtractionResponse(BaseModel):
    """Per-file result of uploading several receipts."""

    total: int
    successful: int
    failed: int
    results: list[DocumentExtractionResponse]
    errors: list[DocumentExtractionError]
