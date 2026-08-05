from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LineaTicket(Base):
    __tablename__ = "linea_ticket"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_ticket: Mapped[str] = mapped_column(ForeignKey("ticket.id_ticket", ondelete="CASCADE"), nullable=False)
    id_producto: Mapped[int] = mapped_column(ForeignKey("producto.id_producto"), nullable=False)
    cantidad_valor: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    cantidad_unidad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    precio: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="lineas")
    producto: Mapped["Producto"] = relationship(back_populates="lineas")
