"""INV-40: el ranking de ventas por producto, los meses por nombre y la etiqueta de alertas con el tipo
(decisiones 1 y 2 de docs/INV-40-requerimientos.md; hallazgos H14 y H15 de docs/INV-35-chat.md)."""
from datetime import date

import pytest

from herramientas.catalogo import (
    MAX_HERRAMIENTAS,
    POR_NOMBRE,
    esquemas,
    normalizar_periodo,
)
from herramientas.core_api import ErrorHerramienta
from tests.test_brechas_catalogo import _admin_la21


@pytest.mark.parametrize(("texto", "fecha", "esperado"), [
    ("diciembre", date(2025, 12, 31), "2025-12"),
    ("diciembre", date(2026, 9, 30), "2025-12"),          # el último diciembre con datos
    ("septiembre", date(2026, 9, 30), "2026-09"),
    ("el mes de Marzo", date(2026, 9, 30), "2026-03"),
    ("dic 2024", None, "2024-12"),
    ("Septiembre de 2025", None, "2025-09"),
    ("setiembre", date(2025, 12, 31), "2025-09"),
    ("2025-11", None, "2025-11"),                          # lo demás pasa igual a rango_periodo
    ("2025-T4", None, "2025-T4"),
])
def test_normalizar_periodo(texto, fecha, esperado):
    assert normalizar_periodo(texto, fecha) == esperado


def test_mes_sin_anio_ni_fecha():
    with pytest.raises(ErrorHerramienta, match="di el año"):
        normalizar_periodo("diciembre", None)


async def test_historial_de_un_mes_por_nombre(ctx, core_api):
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(ctx, h.validar({"periodo": "diciembre"}))).para_modelo
    assert r["periodo_pedido"] == "diciembre" and r["periodo"] == "2025-12-01 a 2025-12-31" and r["agrupacion"] == "mes"
    pedidas = [p for p in core_api.peticiones if p.url.path == "/api/reportes/ventas"]
    assert dict(pedidas[-1].url.params)["fecha_inicio"] == "2025-12-01"


async def test_ranking_del_ultimo_mes(ctx, core_api):
    h = POR_NOMBRE["productos_mas_vendidos"]
    r = await h.ejecutar(ctx, h.validar({}))
    m = r.para_modelo
    assert m["fecha_dato"] == "2025-12-31" and m["periodo"] == "2025-12-01 a 2025-12-31"
    assert m["total"] == m["mostrando"] == 10 and m["filas"][0]["producto"] == "HUEVOS *UND"
    assert m["filas"][0]["participacion"] == "10 %" and m["filas"][0]["valor"].startswith("$ ")
    assert m["orden"].startswith("por valor") and r.data["titulo"] == "Productos más vendidos"
    assert core_api.params() == {"limite": "10", "fecha_inicio": "2025-12-01", "fecha_fin": "2025-12-31"}


async def test_ranking_con_periodo_dias_categoria_y_limite(ctx, core_api):
    h = POR_NOMBRE["productos_mas_vendidos"]
    m = (await h.ejecutar(ctx, h.validar({"periodo": "2025", "categoria": "arroz", "limite": 3}))).para_modelo
    assert m["categoria"] == "Arroz" and len(m["filas"]) == 3 and all(f["categoria"] == "Arroz" for f in m["filas"])
    assert core_api.params()["fecha_inicio"] == "2025-01-01" and core_api.params()["fecha_fin"] == "2025-12-31"
    await h.ejecutar(ctx, h.validar({"dias": 7}))
    assert core_api.params()["fecha_inicio"] == "2025-12-25"
    assert h.etiqueta(h.validar({"sucursal": "GLORIETA", "periodo": "diciembre"})) == \
        "Productos más vendidos · GLORIETA · diciembre"


async def test_ranking_con_los_permisos_del_rol(core_api, core):
    h = POR_NOMBRE["productos_mas_vendidos"]
    propia = (await h.ejecutar(_admin_la21(core), h.validar({}))).para_modelo
    assert core_api.params().get("sucursal_id") is None and propia["filas"]       # el rol lo limita en el Core API
    with pytest.raises(ErrorHerramienta) as e:
        await h.ejecutar(_admin_la21(core), h.validar({"sucursal": "GLORIETA"}))
    assert e.value.status == 403


def test_alertas_muestran_el_tipo_y_lo_piden_solo_si_se_nombra():
    h = POR_NOMBRE["listar_alertas"]
    assert h.etiqueta(h.validar({"sucursal": "GLORIETA", "tipo": "inconsistencia_inventario", "urgencia": "critica"})) \
        == "Alertas · GLORIETA · inconsistencia · crítica"
    tipo = next(e for e in esquemas() if e["function"]["name"] == "listar_alertas")["function"]["parameters"]["properties"]["tipo"]
    assert "Solo si la pregunta nombra el tipo" in tipo["description"]


def test_resumenes_piden_una_sola_llamada():
    for nombre in ("resumen_inventario", "resumen_alertas"):
        sucursal = POR_NOMBRE[nombre].esquema()["function"]["parameters"]["properties"]["sucursal"]
        assert "nunca una llamada por sucursal" in sucursal["description"]


def test_catalogo_de_solo_lectura_y_con_limite():
    assert len(esquemas()) <= MAX_HERRAMIENTAS == 14
    # Solo lectura: GET, salvo el pronóstico, que calcula con POST /api/ml/predict sin escribir nada
    metodos = {(m, ruta) for h in POR_NOMBRE.values() for m, ruta, _ in h.endpoints}
    assert {x for x in metodos if x[0] != "GET"} == {("POST", "/api/ml/predict")}
    assert len(esquemas()) == MAX_HERRAMIENTAS
