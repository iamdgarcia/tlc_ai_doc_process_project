from __future__ import annotations

import pytest

from app.utils.cantidad_parser import parse_cantidad


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("2kg", (2.0, "kg")),
        ("0.428kg", (0.428, "kg")),
        ("0,428 kg", (0.428, "kg")),
        ("200g", (200.0, "g")),
        ("1", (1.0, None)),
        ("2", (2.0, None)),
        ("3", (3.0, None)),
        (None, (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_cantidad(entrada, esperado):
    assert parse_cantidad(entrada) == esperado
