"""Shared catalogue of questions supported by the dashboard chat tools."""

from __future__ import annotations


SUGGESTED_QUESTIONS = [
    {
        "id": "purchase-frequency",
        "label": "Frecuencia de compra",
        "prompt": "¿Cuántas veces he ido a comprar en los últimos 12 meses?",
        "tool_name": "get_purchase_frequency",
    },
    {
        "id": "spending-summary",
        "label": "Resumen de gasto",
        "prompt": "¿Cuánto he gastado en los últimos 12 meses y cuál es mi ticket medio?",
        "tool_name": "get_spending_summary",
    },
    {
        "id": "product-quantities",
        "label": "Cantidades por producto",
        "prompt": "¿Qué cantidad total he comprado de cada producto?",
        "tool_name": "get_product_quantities",
    },
    {
        "id": "price-evolution",
        "label": "Evolución de un precio",
        "prompt": "¿Cómo ha cambiado el precio de pechuga familiar a lo largo del tiempo?",
        "tool_name": "compare_product_prices",
    },
    {
        "id": "recent-purchases",
        "label": "Últimas compras",
        "prompt": "¿Cuáles son mis últimas cinco compras?",
        "tool_name": "get_list_tickets",
    },
]

