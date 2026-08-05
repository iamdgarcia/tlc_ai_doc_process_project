from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Supermercado(Base):
    __tablename__ = "supermercado"

    id_supermercado: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="supermercado")
