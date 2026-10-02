# Módulo 06 — Dashboard de Analíticas

**Ficheros:** `src/app/repositories/analytics.py` · `src/app/api/v1/dashboard.py` · `docs/dashboard_mock.html`
---

## Las queries de analíticas

`AnalyticsRepository` centraliza todas las consultas de análisis. Los mismos métodos los usan el endpoint `/dashboard/report` y las herramientas del agente de chat.

### Gasto total por periodo

```python
def get_spending_summary(self, days: int = 365) -> dict:
    start, end = self._period(days)  # ancla en el último ticket, no en hoy

    row = self._session.execute(
        select(
            func.count(Ticket.id_ticket).label("ticket_count"),
            func.coalesce(func.sum(Ticket.total), 0).label("total_spent"),
            func.coalesce(func.avg(Ticket.total), 0).label("average_ticket"),
        ).where(Ticket.dia >= start, Ticket.dia <= end)
    ).one()

    stores = self._session.execute(
        select(Supermercado.nombre, func.sum(Ticket.total).label("spent"))
        .join(Ticket.supermercado)
        .where(Ticket.dia >= start, Ticket.dia <= end)
        .group_by(Supermercado.nombre)
        .order_by(desc("spent"))
    ).all()
```

**Detalle importante**: el periodo se ancla en el último ticket (`func.max(Ticket.dia)`), no en la fecha de hoy. Si llevas un mes sin subir tickets, `days=30` no devolvería nada si anclara en `datetime.now()`.

### Evolución de precio de un producto

```python
def compare_product_prices(self, product_name: str, days: int = 3650) -> dict:
    # Búsqueda exacta primero, luego búsqueda parcial
    product = self._session.scalar(
        select(Producto).where(func.lower(Producto.nombre) == query).limit(1)
    )
    if product is None:
        product = self._session.scalar(
            select(Producto).where(func.lower(Producto.nombre).contains(query)).limit(1)
        )
    if product is None:
        return {"found": False, "available_examples": [...]}  # sugerencias

    # Historial cronológico de precios
    rows = self._session.execute(
        select(Ticket.dia, Supermercado.nombre, LineaTicket.precio)
        .join(...).order_by(Ticket.dia, Ticket.hora)
    ).all()

    prices = [float(row.precio) for row in rows]
    return {
        "found": True,
        "first_price": prices[0],
        "latest_price": prices[-1],
        "absolute_change": round(prices[-1] - prices[0], 2),
        "percentage_change": round((prices[-1] - prices[0]) / prices[0] * 100, 1),
        "history": [...]
    }
```

### Frecuencia de compra

```python
def get_purchase_frequency(self, days: int = 365) -> dict:
    dates = list(self._session.scalars(
        select(Ticket.dia).where(...).order_by(Ticket.dia)
    ))
    shopping_days = sorted(set(dates))  # días únicos (sin duplicados del mismo día)
    gaps = [(b - a).days for a, b in pairwise(shopping_days)]

    return {
        "ticket_count": len(dates),
        "shopping_days": len(shopping_days),
        "average_visits_per_30_days": round(len(dates) / max(days, 1) * 30, 2),
        "average_days_between_visits": round(sum(gaps) / len(gaps), 1) if gaps else None,
    }
```

`itertools.pairwise` (Python 3.10+) da pares consecutivos de elementos: `[a, b, c]` → `[(a,b), (b,c)]`. Perfecto para calcular diferencias entre fechas consecutivas.

---

## Contrato del endpoint

```
GET /api/v1/dashboard/report
Authorization: Bearer <MASTER_KEY>

Response 200:
{
  "spending_summary": { "total_spent": 1234.56, "stores": [...] },
  "purchase_frequency": { "average_days_between_visits": 4.2 },
  "top_products": [...],
  "price_trends": [...]
}
```

---

## HTML mock

![Dashboard](/docs/dashboard.png)

`docs/dashboard_mock.html` es una página HTML standalone (sin framework) que simula el aspecto del dashboard con datos hardcodeados. Sirve para:

- Validar el diseño antes de tener datos reales
- Mostrar el producto a stakeholders sin necesidad de backend
- Iterar rápido en el layout

FastAPI lo sirve directamente en la ruta raíz `/`:

```python
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_view() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))
```

---

## Siguiente módulo

→ [07 — Evaluaciones con LangSmith](07_evaluaciones.md)
