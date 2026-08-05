from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any


@dataclass(slots=True)
class DocumentRecord:
    """Represents a stored extraction record."""

    id: int
    filename: str
    content_type: str
    extracted_data: dict[str, Any]


class InMemoryDocumentRepository:
    """Simple in-memory repository used as a temporary persistence layer."""

    def __init__(self) -> None:
        self._documents: list[DocumentRecord] = []
        self._id_sequence = count(start=1)

    def save(
        self,
        *,
        filename: str,
        content_type: str,
        extracted_data: dict[str, Any],
    ) -> DocumentRecord:
        """Persist a document extraction result in memory."""

        record = DocumentRecord(
            id=next(self._id_sequence),
            filename=filename,
            content_type=content_type,
            extracted_data=extracted_data,
        )
        self._documents.append(record)
        return record


repository = InMemoryDocumentRepository()
