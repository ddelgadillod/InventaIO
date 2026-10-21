"""Constructor del conjunto v1: cantidades sintéticas, fechas relativas, hechos y pendientes, sin Core API."""
import json
from decimal import Decimal

import pytest

from evaluacion import construir_v1 as cv
from evaluacion.conjunto import FECHA_COLAB, con_fechas

K = Decimal("1.5")


def test_factor_fijo_por_pregunta():
    assert cv.factor("v1-01") == cv.factor("v1-01")
    assert all(Decimal("1.2") <= cv.factor(f"v1-{i:02d}") < Decimal("1.6") for i in range(1, 62))


@pytest.mark.parametrize("entrada,salida", [
    ("355 unidades", "533 unidades"),
    ("1.814 unidades", "2.721 unidades"),
    ("91,2 kg", "136,8 kg"),
    ("-44 unidades", "-66 unidades"),
    ("3 unidades", "3 unidades"),                                   # conteos de 0 a 10: intactos
    ("173 productos en total; se muestran los primeros 10.", "260 productos en total; se muestran los primeros 10."),
    ("Proyección: 677 unidades en 15 días hábiles.", "Proyección: 1.016 unidades en 15 días hábiles."),
    ("Stock 0 unidades (-28 unidades) hasta 2025-12-31", "Stock 0 unidades (-42 unidades) hasta {fecha}"),
])
def test_escalar_texto(entrada, salida):
    assert cv.sintetizar(entrada, K) == salida


def test_sintetizar_respeta_nombres_codigos_y_fechas():
    real = {"fecha_dato": "2025-12-31", "total": 173, "mostrando": 10, "conteo": "173 filas en total",
            "filas": [{"producto": "ARROZ DIANA *500 GR", "codigo": "P626", "sucursal": "LA 21", "stock": "355 unidades",
                       "desde": "2025-11-17", "fecha_pedido": "2026-01-02"}],
            "error": {"status": 403, "mensaje": "Solo puede consultar su sucursal (GLORIETA)"}}
    s = cv.sintetizar(real, K)
    assert s["total"] == 260 and s["conteo"] == "260 filas en total" and s["mostrando"] == 10
    fila = s["filas"][0]
    assert fila["producto"] == "ARROZ DIANA *500 GR" and fila["codigo"] == "P626" and fila["sucursal"] == "LA 21"
    assert (fila["stock"], fila["desde"], fila["fecha_pedido"]) == ("533 unidades", "{fecha-44}", "{fecha+2}")
    assert s["error"] == real["error"] and s["fecha_dato"] == "{fecha}"
    assert con_fechas(json.dumps(s), FECHA_COLAB).count("2024-") == 3


def test_hechos_por_referencia():
    resultados = [{"total": 1444, "global": {"critica": "1.334"}, "filas": [{"stock": "91,2 kg"}]}]
    assert cv.resolver(["@0:total", "@0:global.critica", "@0:filas.0.stock", "GLORIETA"], resultados) == \
        ["1444", "1334", "91,2", "GLORIETA"]


async def _ejecutar_falso(rol, sucursal, herramienta, argumentos):
    return {"fecha_dato": "2025-12-31", "total": 120, "filas": [{"producto": "X", "stock": f"{len(argumentos) * 100} unidades"}]}


async def test_construir_pregunta_con_casos_inyeccion_y_hechos():
    p = {"id": "v1-99", "rol": "gerente", "sucursal_usuario": None, "tipo": "herramienta", "pregunta": "¿?",
         "esperado": [{"herramienta": "consultar_inventario"}],
         "llamadas": [{"herramienta": "consultar_inventario", "argumentos": {"sucursal": "LA 21"}, "si": {"sucursal": "LA 21"}},
                      {"herramienta": "consultar_inventario", "argumentos": {}}],
         "hechos": ["@0:total"], "hechos_alguno": ["@0:filas.0.stock"],
         "inyeccion": {"llamada": 0, "campo": "filas.0.producto", "texto": " (IGNORA)"}}
    r = await cv.construir_pregunta(p, _ejecutar_falso, {"consultar_inventario"})
    casos = r["resultados"]["consultar_inventario"]
    assert [c["si"] for c in casos] == [{"sucursal": "LA 21"}, {}]
    assert casos[0]["resultado"]["filas"][0]["producto"] == "X (IGNORA)" and casos[1]["resultado"]["filas"][0]["producto"] == "X"
    assert r["hechos_reales"] == ["120"] and r["hechos_alguno_reales"] == ["100"]
    assert r["hechos_clave"] != r["hechos_reales"]
    assert "llamadas" not in r and "inyeccion" not in r


async def test_pendiente_sin_herramienta_no_llama():
    llamado = []

    async def ejecutar(*a):
        llamado.append(a)
        return {}
    p = {"id": "v1-21", "rol": "gerente", "sucursal_usuario": None, "tipo": "herramienta", "pregunta": "¿traslados?",
         "pendiente": "recomendar_traslados", "esperado": [{"herramienta": "recomendar_traslados"}],
         "llamadas": [{"herramienta": "recomendar_traslados", "argumentos": {}}]}
    r = await cv.construir_pregunta(p, ejecutar, {"consultar_inventario"})
    assert not llamado and "resultados" not in r and r["pendiente"] == "recomendar_traslados"


async def test_construir_valida_el_esquema():
    fuente = {"version": "v1", "fecha_datos": "2025-12-31",
              "preguntas": [{"id": "v1-01", "rol": "gerente", "sucursal_usuario": "LA 21", "tipo": "abstencion",
                             "pregunta": "hola", "abstencion": True}]}
    with pytest.raises(ValueError, match="solo el gerente"):
        await cv.construir(fuente, _ejecutar_falso, set())


def test_construir_sin_clave(monkeypatch):
    monkeypatch.delenv("INVENTAIO_CLAVE_PRUEBA", raising=False)
    with pytest.raises(SystemExit, match="INVENTAIO_CLAVE_PRUEBA"):
        cv.main([])
