from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from statistics import pstdev

from sqlalchemy import desc, extract, func, select
from sqlalchemy.orm import Session

from app.analytics_questions import SUGGESTED_QUESTIONS
from app.models import LineaTicket, Producto, Supermercado, Ticket
from app.schemas.dashboard import (
    DashboardKpi,
    DashboardPeriod,
    DashboardReport,
    HeatmapSlot,
    PriceSeriesPoint,
    ProductPriceReport,
    ProductQuantityReport,
    PurchaseDistribution,
    PurchaseDistributionPoint,
    RecentTicketReport,
    SpendingPoint,
    StoreReport,
    SuggestedQuestion,
    TopProductReport,
    VisitSummary,
)

SPANISH_MONTHS = [
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
]

SPANISH_DAYS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]


class DashboardRepository:
    """Run the aggregation queries used by the dashboard report."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_report(self) -> DashboardReport:
        """Build the dashboard response from the persisted ticket data."""

        anchor_date = self._get_anchor_date()
        period_start = self._first_day_of_month(self._shift_months(anchor_date, -11))
        period_end = anchor_date
        previous_start = self._first_day_of_month(self._shift_months(period_start, -12))
        previous_end = period_start - timedelta(days=1)

        current_total = self._sum_ticket_total(period_start, period_end)
        previous_total = self._sum_ticket_total(previous_start, previous_end)
        current_ticket_count = self._count_tickets(period_start, period_end)
        previous_ticket_count = self._count_tickets(previous_start, previous_end)

        product_stats = self._fetch_product_stats(period_start, period_end)
        spending_trend = self._fetch_spending_trend(period_start, period_end)
        heatmap = self._fetch_purchase_heatmap(period_start, period_end)
        price_reports = self._fetch_price_reports(period_start, period_end, product_stats)
        visit_summary = self._fetch_visit_summary(period_start, period_end)

        summary = [
            DashboardKpi(
                name="Gasto",
                value=self._format_currency(current_total),
                delta=self._format_percent_change(current_total, previous_total),
                note="Vs. periodo anterior",
            ),
            DashboardKpi(
                name="Tickets",
                value=str(current_ticket_count),
                delta=self._format_percent_change(
                    float(current_ticket_count),
                    float(previous_ticket_count),
                ),
                note="Vs. periodo anterior",
            ),
            DashboardKpi(
                name="Productos",
                value=str(len(product_stats)),
                delta=self._format_top20_share(product_stats, current_total),
                note="Concentración del gasto",
            ),
            DashboardKpi(
                name="Ahorro",
                value=self._format_currency(self._estimate_savings(product_stats)),
                delta="Potencial",
                note="Si compras al mínimo histórico",
            ),
        ]

        highlights = self._build_highlights(heatmap, product_stats, price_reports)

        return DashboardReport(
            project_name="Luma Spend",
            generated_at=anchor_date.isoformat(),
            period=DashboardPeriod(
                label="Últimos 12 meses",
                start_date=period_start.isoformat(),
                end_date=period_end.isoformat(),
            ),
            summary=summary,
            visit_summary=visit_summary,
            spending_trend=spending_trend,
            top_products=[
                TopProductReport(
                    product_name=row["product_name"],
                    total_spent=row["total_spent"],
                    purchase_count=row["purchase_count"],
                    average_price=row["average_price"],
                )
                for row in product_stats[:4]
            ],
            product_quantities=self._fetch_product_quantities(period_start, period_end),
            stores=self._fetch_stores(period_start, period_end),
            recent_tickets=self._fetch_recent_tickets(period_start, period_end),
            purchase_heatmap=heatmap,
            purchase_distribution=self._fetch_purchase_distribution(period_start, period_end),
            price_reports=price_reports,
            highlights=highlights,
            suggested_questions=[SuggestedQuestion(**question) for question in SUGGESTED_QUESTIONS],
        )

    def _fetch_visit_summary(self, start_date: date, end_date: date) -> VisitSummary:
        rows = self._session.execute(
            select(Ticket.dia, Ticket.total)
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .order_by(Ticket.dia, Ticket.hora)
        ).all()
        dates = [row.dia for row in rows]
        unique_dates = sorted(set(dates))
        gaps = [
            (current - previous).days
            for previous, current in pairwise(unique_dates)
        ]
        month_count = max(
            1,
            (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1,
        )
        ticket_count = len(rows)
        total = sum(float(row.total or 0) for row in rows)
        return VisitSummary(
            ticket_count=ticket_count,
            shopping_days=len(unique_dates),
            average_visits_per_month=round(ticket_count / month_count, 2),
            average_days_between_visits=(round(sum(gaps) / len(gaps), 1) if gaps else None),
            average_ticket=round(total / ticket_count, 2) if ticket_count else 0.0,
            first_visit=unique_dates[0].isoformat() if unique_dates else None,
            last_visit=unique_dates[-1].isoformat() if unique_dates else None,
        )

    def _fetch_purchase_distribution(
        self, start_date: date, end_date: date
    ) -> PurchaseDistribution:
        monthly_rows = self._session.execute(
            select(
                extract("year", Ticket.dia).label("year"),
                extract("month", Ticket.dia).label("month"),
                func.count(Ticket.id_ticket).label("purchase_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by("year", "month")
        ).all()
        monthly = {
            (int(row.year), int(row.month)): (int(row.purchase_count), float(row.total_spent))
            for row in monthly_rows
        }
        months: list[PurchaseDistributionPoint] = []
        cursor = self._first_day_of_month(start_date)
        while cursor <= end_date:
            count, spent = monthly.get((cursor.year, cursor.month), (0, 0.0))
            months.append(
                PurchaseDistributionPoint(
                    label=f"{SPANISH_MONTHS[cursor.month - 1]} {str(cursor.year)[2:]}",
                    purchase_count=count,
                    total_spent=spent,
                )
            )
            cursor = self._shift_months(cursor, 1)

        weekday_rows = self._session.execute(
            select(
                extract("dow", Ticket.dia).label("bucket"),
                func.count(Ticket.id_ticket).label("purchase_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by("bucket")
        ).all()
        by_weekday = {
            int(row.bucket): (int(row.purchase_count), float(row.total_spent))
            for row in weekday_rows
        }
        weekday_order = [1, 2, 3, 4, 5, 6, 0]
        weekdays = [
            PurchaseDistributionPoint(
                label=SPANISH_DAYS[index],
                purchase_count=by_weekday.get(index, (0, 0.0))[0],
                total_spent=by_weekday.get(index, (0, 0.0))[1],
            )
            for index in weekday_order
        ]

        hour_rows = self._session.execute(
            select(
                extract("hour", Ticket.hora).label("bucket"),
                func.count(Ticket.id_ticket).label("purchase_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by("bucket")
        ).all()
        by_hour = {
            int(row.bucket): (int(row.purchase_count), float(row.total_spent))
            for row in hour_rows
        }
        hours = [
            PurchaseDistributionPoint(
                label=f"{hour:02d}:00",
                purchase_count=by_hour.get(hour, (0, 0.0))[0],
                total_spent=by_hour.get(hour, (0, 0.0))[1],
            )
            for hour in range(24)
        ]
        return PurchaseDistribution(months=months, weekdays=weekdays, hours=hours)

    def _fetch_product_quantities(
        self, start_date: date, end_date: date
    ) -> list[ProductQuantityReport]:
        rows = self._session.execute(
            select(
                Producto.nombre.label("product_name"),
                LineaTicket.cantidad_unidad.label("unit"),
                func.coalesce(func.sum(LineaTicket.cantidad_valor), 0).label("total_quantity"),
                func.count(LineaTicket.id).label("purchase_count"),
                func.coalesce(func.sum(LineaTicket.precio), 0).label("total_spent"),
            )
            .join(LineaTicket.producto)
            .join(LineaTicket.ticket)
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by(Producto.id_producto, Producto.nombre, LineaTicket.cantidad_unidad)
            .order_by(desc("purchase_count"), desc("total_quantity"))
        ).all()
        return [
            ProductQuantityReport(
                product_name=row.product_name,
                total_quantity=float(row.total_quantity or 0),
                unit=row.unit,
                purchase_count=int(row.purchase_count or 0),
                total_spent=float(row.total_spent or 0),
            )
            for row in rows
        ]

    def _fetch_stores(self, start_date: date, end_date: date) -> list[StoreReport]:
        rows = self._session.execute(
            select(
                Supermercado.nombre.label("store_name"),
                func.count(Ticket.id_ticket).label("ticket_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .join(Ticket.supermercado)
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by(Supermercado.id_supermercado, Supermercado.nombre)
            .order_by(desc("total_spent"))
        ).all()
        return [
            StoreReport(
                store_name=row.store_name,
                ticket_count=int(row.ticket_count or 0),
                total_spent=float(row.total_spent or 0),
            )
            for row in rows
        ]

    def _fetch_recent_tickets(
        self, start_date: date, end_date: date, limit: int = 5
    ) -> list[RecentTicketReport]:
        rows = self._session.execute(
            select(
                Ticket.id_ticket,
                Ticket.dia,
                Ticket.total,
                Supermercado.nombre.label("store_name"),
            )
            .join(Ticket.supermercado)
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .order_by(Ticket.dia.desc(), Ticket.hora.desc())
            .limit(limit)
        ).all()
        return [
            RecentTicketReport(
                ticket_id=row.id_ticket,
                store_name=row.store_name,
                date=row.dia.isoformat(),
                total=float(row.total or 0),
            )
            for row in rows
        ]

    def _get_anchor_date(self) -> date:
        """Use the latest ticket date when available, otherwise today."""

        latest_date = self._session.scalar(select(func.max(Ticket.dia)))
        return latest_date or datetime.now(timezone.utc).date()

    def _sum_ticket_total(self, start_date: date, end_date: date) -> float:
        """Return the sum of ticket totals in the requested period."""

        total = self._session.scalar(
            select(func.coalesce(func.sum(Ticket.total), 0)).where(
                Ticket.dia >= start_date,
                Ticket.dia <= end_date,
            )
        )
        return float(total or 0)

    def _count_tickets(self, start_date: date, end_date: date) -> int:
        """Return the number of tickets in the requested period."""

        count = self._session.scalar(
            select(func.count(Ticket.id_ticket)).where(
                Ticket.dia >= start_date,
                Ticket.dia <= end_date,
            )
        )
        return int(count or 0)

    def _fetch_product_stats(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, float | int | str]]:
        """Aggregate the spend per product for the requested period."""

        stmt = (
            select(
                Producto.id_producto.label("product_id"),
                Producto.nombre.label("product_name"),
                func.coalesce(func.sum(LineaTicket.precio), 0).label("total_spent"),
                func.count(LineaTicket.id).label("purchase_count"),
                func.coalesce(func.avg(LineaTicket.precio), 0).label("average_price"),
                func.coalesce(func.min(LineaTicket.precio), 0).label("min_price"),
                func.coalesce(func.max(LineaTicket.precio), 0).label("max_price"),
            )
            .join(LineaTicket.producto)
            .join(LineaTicket.ticket)
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by(Producto.id_producto, Producto.nombre)
            .order_by(desc("total_spent"), desc("purchase_count"))
        )

        rows = self._session.execute(stmt).all()
        return [
            {
                "product_id": int(row.product_id),
                "product_name": row.product_name,
                "total_spent": float(row.total_spent or 0),
                "purchase_count": int(row.purchase_count or 0),
                "average_price": float(row.average_price or 0),
                "min_price": float(row.min_price or 0),
                "max_price": float(row.max_price or 0),
            }
            for row in rows
        ]

    def _fetch_spending_trend(
        self,
        start_date: date,
        end_date: date,
    ) -> list[SpendingPoint]:
        """Return monthly ticket totals for the dashboard chart."""

        stmt = (
            select(
                extract("year", Ticket.dia).label("year"),
                extract("month", Ticket.dia).label("month"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by("year", "month")
            .order_by("year", "month")
        )
        rows = self._session.execute(stmt).all()
        totals_by_month = {
            (int(row.year), int(row.month)): float(row.total_spent or 0)
            for row in rows
        }

        points: list[SpendingPoint] = []
        cursor = self._first_day_of_month(start_date)
        while cursor <= end_date:
            points.append(
                SpendingPoint(
                    label=SPANISH_MONTHS[cursor.month - 1],
                    total_spent=totals_by_month.get((cursor.year, cursor.month), 0.0),
                )
            )
            cursor = self._shift_months(cursor, 1)

        return points

    def _fetch_purchase_heatmap(
        self,
        start_date: date,
        end_date: date,
    ) -> list[HeatmapSlot]:
        """Aggregate tickets by day of week and hour."""

        stmt = (
            select(
                extract("dow", Ticket.dia).label("dow"),
                extract("hour", Ticket.hora).label("hour"),
                func.count(Ticket.id_ticket).label("purchase_count"),
                func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            )
            .where(Ticket.dia >= start_date, Ticket.dia <= end_date)
            .group_by("dow", "hour")
            .order_by(desc("purchase_count"), desc("total_spent"))
        )

        rows = self._session.execute(stmt).all()
        return [
            HeatmapSlot(
                day=SPANISH_DAYS[int(row.dow) % 7],
                hour=f"{int(row.hour):02d}:00",
                purchase_count=int(row.purchase_count or 0),
                total_spent=float(row.total_spent or 0),
            )
            for row in rows
        ]

    def _fetch_price_reports(
        self,
        start_date: date,
        end_date: date,
        product_stats: list[dict[str, float | int | str]],
    ) -> list[ProductPriceReport]:
        """Build product price analytics for the most relevant products."""

        reports: list[ProductPriceReport] = []
        for product in product_stats[:6]:
            product_id = int(product["product_id"])
            series_rows = self._session.execute(
                select(
                    extract("year", Ticket.dia).label("year"),
                    extract("month", Ticket.dia).label("month"),
                    func.coalesce(func.avg(LineaTicket.precio), 0).label("price"),
                )
                .join(LineaTicket.ticket)
                .where(
                    LineaTicket.id_producto == product_id,
                    Ticket.dia >= start_date,
                    Ticket.dia <= end_date,
                )
                .group_by("year", "month")
                .order_by("year", "month")
            ).all()

            monthly_prices = [float(row.price or 0) for row in series_rows]
            if series_rows:
                latest_row = series_rows[-1]
                current_price = float(latest_row.price or 0)
            else:
                current_price = float(product["average_price"] or 0)

            reports.append(
                ProductPriceReport(
                    product_name=str(product["product_name"]),
                    current_price=current_price,
                    min_price=float(product["min_price"] or 0),
                    max_price=float(product["max_price"] or 0),
                    average_price=float(product["average_price"] or 0),
                    volatility=self._compute_volatility(monthly_prices),
                    trend=self._compute_trend(monthly_prices),
                    series=[
                        PriceSeriesPoint(
                            label=SPANISH_MONTHS[int(row.month) - 1],
                            price=float(row.price or 0),
                        )
                        for row in series_rows
                    ],
                )
            )

        return reports

    def _build_highlights(
        self,
        heatmap: list[HeatmapSlot],
        product_stats: list[dict[str, float | int | str]],
        price_reports: list[ProductPriceReport],
    ) -> list[str]:
        """Generate concise human-readable insights for the dashboard."""

        highlights: list[str] = []

        if heatmap:
            top_slot = heatmap[0]
            highlights.append(
                f"El pico de compras se concentra en {top_slot.day} {top_slot.hour}."
            )

        if product_stats:
            top_product = product_stats[0]
            highlights.append(
                f"{top_product['product_name']} lidera el gasto con {self._format_currency(top_product['total_spent'])}."
            )

        if price_reports:
            price_report = price_reports[0]
            highlights.append(
                f"{price_report.product_name} muestra una tendencia {price_report.trend}."
            )

        if not highlights:
            highlights.append("Aún no hay tickets suficientes para generar insights.")

        return highlights[:3]

    def _estimate_savings(self, product_stats: list[dict[str, float | int | str]]) -> float:
        """Estimate savings by comparing average and minimum prices."""

        savings = 0.0
        for row in product_stats:
            purchase_count = float(row["purchase_count"] or 0)
            average_price = float(row["average_price"] or 0)
            min_price = float(row["min_price"] or 0)
            if average_price > min_price:
                savings += (average_price - min_price) * purchase_count
        return savings

    def _format_top20_share(
        self,
        product_stats: list[dict[str, float | int | str]],
        total_spent: float,
    ) -> str:
        """Format the share of spend concentrated in the top 20 products."""

        if total_spent <= 0:
            return "Top 20 = 0%"

        top20_total = sum(float(row["total_spent"] or 0) for row in product_stats[:20])
        share = (top20_total / total_spent) * 100
        return f"Top 20 = {share:.0f}%"

    def _compute_volatility(self, values: list[float]) -> float:
        """Compute a simple standard deviation for a price series."""

        if len(values) < 2:
            return 0.0
        return float(pstdev(values))

    def _compute_trend(self, values: list[float]) -> str:
        """Classify a price trend from the first and last observed values."""

        if len(values) < 2:
            return "estable"

        first_value = values[0]
        last_value = values[-1]
        if first_value == 0:
            return "estable"

        change = (last_value - first_value) / first_value
        if change > 0.03:
            return "creciente"
        if change < -0.03:
            return "decreciente"
        return "estable"

    def _format_currency(self, value: float) -> str:
        """Render a float value as a Spanish euro string."""

        return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    def _format_percent_change(self, current: float, previous: float) -> str:
        """Format the percentage variation between two values."""

        if previous <= 0:
            return "-"

        delta = ((current - previous) / previous) * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}%"

    def _first_day_of_month(self, value: date) -> date:
        """Return the first day of the month for a given date."""

        return value.replace(day=1)

    def _shift_months(self, value: date, months: int) -> date:
        """Move a date by a number of months while preserving valid days."""

        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)
