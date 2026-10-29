"""INV-33 (B4) — Agrupaciones de los reportes de ventas: las de siempre y las nuevas, trimestre y año."""
import pytest

from reportes.router import _expr_agrupacion


@pytest.mark.parametrize("pedida,normalizada,formato", [
    ("dia", "dia", "YYYY-MM-DD"), ("semana", "semana", "IW"), ("mes", "mes", "YYYY-MM"),
    ("trimestre", "trimestre", "'Q'"), ("anio", "anio", "'YYYY')"), ("otra", "dia", "YYYY-MM-DD"),
])
def test_agrupaciones(pedida, normalizada, formato):
    expresion, agrupacion = _expr_agrupacion(pedida)
    assert agrupacion == normalizada and formato in expresion
