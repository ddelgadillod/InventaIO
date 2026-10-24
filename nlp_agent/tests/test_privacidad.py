"""Las ventas reales en pesos no llegan al repositorio (INV-33, B4)."""
import json
from decimal import Decimal

from evaluacion.construir_v1 import sintetizar_resultado
from evaluacion.privacidad import sin_pesos, tiene_pesos

# Forma del resultado de historial_ventas; los pesos son ilustrativos
VENTAS = {"agrupacion": "anio", "totales": {"cantidad": "42.434 unidades", "valor": "$ 84.720.439", "margen": "$ 5.536.390"},
          "filas": [{"periodo": "2025", "cantidad": "13.181 unidades", "valor": "$ 26.251.950", "margen": "$ 1.642.258"}]}


def test_quita_las_cifras_en_pesos():
    assert sin_pesos("Vendió $ 84.720.439, unos 84,7 millones de pesos") == "Vendió $ [omitido], unos $ [omitido]"
    assert sin_pesos({"filas": [{"valor": "$ 1.000", "cantidad": "42.434 unidades"}]}) == \
        {"filas": [{"valor": "$ [omitido]", "cantidad": "42.434 unidades"}]}
    assert not tiene_pesos("42.434 unidades en 2025, 13 periodos")


def test_el_sintetico_de_ventas_usa_pesos_ilustrativos():
    r = sintetizar_resultado("historial_ventas", VENTAS, Decimal("1.20"))
    assert r["filas"][0] == {"periodo": "{periodo:anio}", "cantidad": "15.817 unidades", "valor": "$ 31.634.000", "margen": "$ 2.372.550"}
    assert r["totales"]["valor"] == "$ 101.842.000"                          # 50.921 × 2.000, no 84.720.439 × 1,20
    assert "26.251.950" not in json.dumps(r) and "31.502.340" not in json.dumps(r)


def test_el_conjunto_v1_no_trae_pesos_reales():
    from evaluacion.conjunto import DIRECTORIO
    for p in json.loads((DIRECTORIO / "v1" / "preguntas.json").read_text(encoding="utf-8"))["preguntas"]:
        for r in [p.get("resultados", {})]:
            texto = json.dumps(r, ensure_ascii=False)
            if "historial_ventas" in r and "$ " in texto:
                casos = r["historial_ventas"] if isinstance(r["historial_ventas"], list) else [{"resultado": r["historial_ventas"]}]
                for c in casos:
                    t = c["resultado"]["totales"]
                    cantidad = int(t["cantidad"].split()[0].replace(".", "").split(",")[0])
                    assert t["valor"].replace("$ ", "").replace(".", "").startswith(str(cantidad * 2000)[:6])
