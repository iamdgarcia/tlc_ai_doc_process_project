from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Ticket(Base):
    __tablename__ = "ticket"

    id_ticket: Mapped[str] = mapped_column(String(50), primary_key=True)
    id_supermercado: Mapped[int] = mapped_column(ForeignKey("supermercado.id_supermercado"), nullable=False)
    dia: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    hora: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    supermercado: Mapped["Supermercado"] = relationship(back_populates="tickets")
    lineas: Mapped[list["LineaTicket"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")
