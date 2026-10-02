from __future__ import annotations

import re


def parse_cantidad(s: str | None) -> tuple[float | None, str | None]:
    """Split a quantity string into numeric value and unit.

    Examples:
        "2kg"    -> (2.0, "kg")
        "200g"   -> (200.0, "g")
        "1"      -> (1.0, None)
        None     -> (None, None)
    """
    if not s:
        return None, None

    normalized = s.strip().replace(",", ".")
    match = re.match(r"^(\d+\.?\d*)\s*([a-zA-Z]*)$", normalized)
    if not match:
        return None, None

    valor = float(match.group(1))
    unidad = match.group(2).lower() or None
    return valor, unidad
