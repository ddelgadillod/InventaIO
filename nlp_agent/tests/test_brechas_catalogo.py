"""Herramientas nuevas de las brechas del catálogo (INV-33): resumen_inventario (B2) y recomendar_traslados (B3),
contra el Core API simulado con filas reales del 21-oct."""
import pytest

from herramientas.catalogo import POR_NOMBRE
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta


def _admin_la21(core):
    return Contexto(core, "Bearer token-la21", "req-1")          # el admin de LA 21 del Core API simulado


async def test_resumen_inventario_global_y_en_riesgo(ctx, core_api):
    h = POR_NOMBRE["resumen_inventario"]
    r = (await h.ejecutar(ctx, h.validar({}))).para_modelo
    assert r["fecha_dato"] == "2025-12-31" and {f["sucursal"] for f in r["filas"]} >= {"PRINCIPAL", "GLORIETA"}
    g = r["global"]
    assert int(g["en_riesgo"]) == int(g["bajo"]) + int(g["critico"])       # bajo + crítico, como el dashboard
    assert core_api.params() == {}
    r = (await h.ejecutar(ctx, h.validar({"sucursal": "glorieta"}))).para_modelo
    assert [f["sucursal"] for f in r["filas"]] == ["GLORIETA"] and core_api.params() == {"sucursal_id": "3"}


async def test_traslados_por_direccion(ctx, core_api):
    h = POR_NOMBRE["recomendar_traslados"]
    hacia = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL", "direccion": "hacia"}))).para_modelo
    assert hacia["total"] == 4 and all(f["destino"] == "PRINCIPAL" for f in hacia["filas"])
    desde = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL", "direccion": "desde"}))).para_modelo
    assert desde["total"] == 1 and desde["filas"][0]["destino"] == "LA 21"
    ambas = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL"}))).para_modelo
    assert ambas["total"] == 5 and "traslados en total" in ambas["conteo"]
    assert core_api.params() == {"sucursal": "PRINCIPAL"}                    # la dirección no viaja al Core API


async def test_traslados_orden_y_llegada_tarde(ctx):
    h = POR_NOMBRE["recomendar_traslados"]
    r = (await h.ejecutar(ctx, h.validar({}))).para_modelo
    urgencias = [f["urgencia"] for f in r["filas"]]
    assert urgencias == sorted(urgencias, key=["urgente", "alta", "normal", "vigilancia"].index)
    assert r["filas"][0]["producto"].startswith("DURAZNO") and r["filas"][0]["llega_tarde"] is True   # 0 días: primero
    assert r["llegan_tarde"] == "1" and r["filas"][0]["cantidad"] == "13 unidades"
    assert h.lenta(h.validar({})) and h.etiqueta(h.validar({"sucursal": "PRINCIPAL", "direccion": "hacia", "urgencia": "urgente"})) \
        == "Traslados sugeridos · hacia PRINCIPAL · urgente"


async def test_traslados_permisos_del_rol(core_api, core):
    h = POR_NOMBRE["recomendar_traslados"]
    propia = (await h.ejecutar(_admin_la21(core), h.validar({"direccion": "hacia"}))).para_modelo
    assert propia["filtro"] == {"sucursal": "LA 21", "direccion": "hacia", "por_tu_rol": True}
    assert [f["destino"] for f in propia["filas"]] == ["LA 21"]
    with pytest.raises(ErrorHerramienta) as e:
        await h.ejecutar(_admin_la21(core), h.validar({"sucursal": "GLORIETA"}))
    assert e.value.status == 403
