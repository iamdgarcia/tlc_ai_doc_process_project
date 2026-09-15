from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardPeriod(BaseModel):
    """Time range covered by the dashboard report."""

    label: str = Field(..., examples=["Últimos 12 meses"])
    start_date: str = Field(..., examples=["2025-08-01"])
    end_date: str = Field(..., examples=["2026-07-31"])


class DashboardKpi(BaseModel):
    """Headline metric displayed in the dashboard header."""

    name: str = Field(..., examples=["Gasto"])
    value: str = Field(..., examples=["1.284,70 €"])
    delta: str = Field(..., examples=["+8,4%"])
    note: str = Field(..., examples=["Seguimiento de precios"])


class SpendingPoint(BaseModel):
    """Single point in the spending evolution chart."""

    label: str = Field(..., examples=["Ene"])
    total_spent: float = Field(..., examples=[124.8])


class TopProductReport(BaseModel):
    """Aggregated spend summary for one product."""

    product_name: str = Field(..., examples=["Leche semidesnatada"])
    total_spent: float = Field(..., examples=[74.2])
    purchase_count: int = Field(..., examples=[28])
    average_price: float = Field(..., examples=[1.98])


class VisitSummary(BaseModel):
    """Purchase-frequency metrics for the selected period."""

    ticket_count: int
    shopping_days: int
    average_visits_per_month: float
    average_days_between_visits: float | None
    average_ticket: float
    first_visit: str | None
    last_visit: str | None


class ProductQuantityReport(BaseModel):
    """Purchased quantity grouped by normalized product and unit."""

    product_name: str
    total_quantity: float
    unit: str | None
    purchase_count: int
    total_spent: float


class StoreReport(BaseModel):
    """Spend and visit count for one supermarket."""

    store_name: str
    ticket_count: int
    total_spent: float


class RecentTicketReport(BaseModel):
    """Small ticket projection used by the dashboard activity feed."""

    ticket_id: str
    store_name: str
    date: str
    total: float


class SuggestedQuestion(BaseModel):
    """A common question that can be sent directly to the chat agent."""

    id: str
    label: str
    prompt: str
    tool_name: str


class HeatmapSlot(BaseModel):
    """Single cell of the purchase heatmap."""

    day: str = Field(..., examples=["Vie"])
    hour: str = Field(..., examples=["18:00"])
    purchase_count: int = Field(..., examples=[5])
    total_spent: float = Field(..., examples=[41.2])


class PurchaseDistributionPoint(BaseModel):
    """Ticket count and spend for one time bucket."""

    label: str
    purchase_count: int
    total_spent: float


class PurchaseDistribution(BaseModel):
    """Purchase distribution by month, weekday and hour."""

    months: list[PurchaseDistributionPoint]
    weekdays: list[PurchaseDistributionPoint]
    hours: list[PurchaseDistributionPoint]


class PriceSeriesPoint(BaseModel):
    """Price history point for one product."""

    label: str = Field(..., examples=["Ago"])
    price: float = Field(..., examples=[1.72])


class ProductPriceReport(BaseModel):
    """Price analytics for one product."""

    product_name: str = Field(..., examples=["Leche semidesnatada"])
    current_price: float = Field(..., examples=[1.98])
    min_price: float = Field(..., examples=[1.69])
    max_price: float = Field(..., examples=[2.15])
    average_price: float = Field(..., examples=[1.93])
    volatility: float = Field(..., examples=[0.12])
    trend: str = Field(..., examples=["estable"])
    series: list[PriceSeriesPoint]


class DashboardReport(BaseModel):
    """Contract returned by the dashboard report endpoint."""

    project_name: str = Field(..., examples=["Luma Spend"])
    generated_at: str = Field(..., examples=["2026-07-29T12:00:00Z"])
    period: DashboardPeriod
    summary: list[DashboardKpi]
    visit_summary: VisitSummary
    spending_trend: list[SpendingPoint]
    top_products: list[TopProductReport]
    product_quantities: list[ProductQuantityReport]
    stores: list[StoreReport]
    recent_tickets: list[RecentTicketReport]
    purchase_heatmap: list[HeatmapSlot]
    purchase_distribution: PurchaseDistribution
    price_reports: list[ProductPriceReport]
    highlights: list[str]
    suggested_questions: list[SuggestedQuestion]
