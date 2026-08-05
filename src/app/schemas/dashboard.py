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


class HeatmapSlot(BaseModel):
    """Single cell of the purchase heatmap."""

    day: str = Field(..., examples=["Vie"])
    hour: str = Field(..., examples=["18:00"])
    purchase_count: int = Field(..., examples=[5])
    total_spent: float = Field(..., examples=[41.2])


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
    spending_trend: list[SpendingPoint]
    top_products: list[TopProductReport]
    purchase_heatmap: list[HeatmapSlot]
    price_reports: list[ProductPriceReport]
    highlights: list[str]
