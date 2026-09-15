"""Read-only analytics queries exposed to the conversational agent."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import pairwise

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import LineaTicket, Producto, Supermercado, Ticket


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _safe_int(value: object, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    def _period(self, days: int) -> tuple[date, date]:
        safe_days = self._safe_int(days, 365, 1, 3650)
        anchor = self._session.scalar(select(func.max(Ticket.dia))) or datetime.now(
            timezone.utc
        ).date()
        return anchor - timedelta(days=safe_days - 1), anchor

    def get_purchase_frequency(self, days: int = 365) -> dict:
        days = self._safe_int(days, 365, 1, 3650)
        start, end = self._period(days)
        dates = list(
            self._session.scalars(
                select(Ticket.dia)
                .where(Ticket.dia >= start, Ticket.dia <= end)
                .order_by(Ticket.dia, Ticket.hora)
            )
        )
        shopping_days = sorted(set(dates))
        gaps = [
            (current - previous).days
            for previous, current in pairwise(shopping_days)
        ]
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "ticket_count": len(dates),
            "shopping_days": len(shopping_days),
            "average_visits_per_30_days": round(len(dates) / max(days, 1) * 30, 2),
            "average_days_between_visits": round(sum(gaps) / len(gaps), 1) if gaps else None,
        }

    def get_spending_summary(self, days: int = 365) -> dict:
        days = self._safe_int(days, 365, 1, 3650)
        start, end = self._period(days)
        row = self._session.execute(
            select(
                func.count(Ticket.id_ticket).label("ticket_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
                func.coalesce(func.avg(Ticket.total), 0).label("average_ticket"),
                func.coalesce(func.min(Ticket.total), 0).label("minimum_ticket"),
                func.coalesce(func.max(Ticket.total), 0).label("maximum_ticket"),
            ).where(Ticket.dia >= start, Ticket.dia <= end)
        ).one()
        stores = self._session.execute(
            select(
                Supermercado.nombre,
                func.count(Ticket.id_ticket).label("visits"),
                func.coalesce(func.sum(Ticket.total), 0).label("spent"),
            )
            .join(Ticket.supermercado)
            .where(Ticket.dia >= start, Ticket.dia <= end)
            .group_by(Supermercado.id_supermercado, Supermercado.nombre)
            .order_by(desc("spent"))
        ).all()
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "ticket_count": int(row.ticket_count or 0),
            "total_spent": float(row.total_spent or 0),
            "average_ticket": float(row.average_ticket or 0),
            "minimum_ticket": float(row.minimum_ticket or 0),
            "maximum_ticket": float(row.maximum_ticket or 0),
            "currency": "EUR",
            "stores": [
                {"name": item.nombre, "visits": int(item.visits), "spent": float(item.spent)}
                for item in stores
            ],
        }

    def get_product_quantities(self, days: int = 365, limit: int = 20) -> dict:
        days = self._safe_int(days, 365, 1, 3650)
        start, end = self._period(days)
        safe_limit = self._safe_int(limit, 20, 1, 100)
        rows = self._session.execute(
            select(
                Producto.nombre.label("product"),
                LineaTicket.cantidad_unidad.label("unit"),
                func.coalesce(func.sum(LineaTicket.cantidad_valor), 0).label("quantity"),
                func.count(LineaTicket.id).label("times_purchased"),
                func.coalesce(func.sum(LineaTicket.precio), 0).label("spent"),
            )
            .join(LineaTicket.producto)
            .join(LineaTicket.ticket)
            .where(Ticket.dia >= start, Ticket.dia <= end)
            .group_by(Producto.id_producto, Producto.nombre, LineaTicket.cantidad_unidad)
            .order_by(desc("times_purchased"), desc("quantity"))
            .limit(safe_limit)
        ).all()
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "note": "Quantities with different units are deliberately kept separate.",
            "products": [
                {
                    "name": row.product,
                    "quantity": float(row.quantity or 0),
                    "unit": row.unit or "units",
                    "times_purchased": int(row.times_purchased or 0),
                    "spent": float(row.spent or 0),
                }
                for row in rows
            ],
        }

    def compare_product_prices(self, product_name: str, days: int = 3650) -> dict:
        days = self._safe_int(days, 3650, 1, 3650)
        start, end = self._period(days)
        query = (product_name or "").strip().lower()
        product = self._session.scalar(
            select(Producto)
            .where(func.lower(Producto.nombre) == query)
            .limit(1)
        )
        if product is None and query:
            product = self._session.scalar(
                select(Producto)
                .where(func.lower(Producto.nombre).contains(query))
                .order_by(Producto.nombre)
                .limit(1)
            )
        if product is None:
            suggestions = list(
                self._session.scalars(select(Producto.nombre).order_by(Producto.nombre).limit(12))
            )
            return {"found": False, "query": product_name, "available_examples": suggestions}

        rows = self._session.execute(
            select(
                Ticket.dia,
                Ticket.id_ticket,
                Supermercado.nombre.label("store"),
                LineaTicket.precio,
                LineaTicket.cantidad_valor,
                LineaTicket.cantidad_unidad,
            )
            .join(LineaTicket.ticket)
            .join(Ticket.supermercado)
            .where(
                LineaTicket.id_producto == product.id_producto,
                Ticket.dia >= start,
                Ticket.dia <= end,
                LineaTicket.precio.is_not(None),
            )
            .order_by(Ticket.dia, Ticket.hora)
        ).all()
        prices = [float(row.precio) for row in rows]
        first = prices[0] if prices else None
        last = prices[-1] if prices else None
        return {
            "found": True,
            "product": product.nombre,
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "observations": len(rows),
            "first_price": first,
            "latest_price": last,
            "absolute_change": round(last - first, 2) if first is not None and last is not None else None,
            "percentage_change": (
                round((last - first) / first * 100, 1)
                if first not in (None, 0) and last is not None
                else None
            ),
            "minimum_price": min(prices) if prices else None,
            "maximum_price": max(prices) if prices else None,
            "history": [
                {
                    "date": row.dia.isoformat(),
                    "ticket_id": row.id_ticket,
                    "store": row.store,
                    "price": float(row.precio),
                    "quantity": float(row.cantidad_valor) if row.cantidad_valor is not None else None,
                    "unit": row.cantidad_unidad,
                }
                for row in rows
            ],
        }
