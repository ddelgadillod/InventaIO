"""Herramientas nuevas de las brechas del catálogo (INV-33): resumen_inventario (B2) y recomendar_traslados (B3),
contra el Core API simulado con filas reales del 21-oct."""
import pytest

from herramientas.base import ErrorArgumentos
from herramientas.catalogo import POR_NOMBRE
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta
from tests import core_falso


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


async def test_traslados_por_destino_y_origen(ctx, core_api):
    """P6 (23-oct): destino («mover a X») y origen («desde X») en vez de sucursal y dirección."""
    h = POR_NOMBRE["recomendar_traslados"]
    hacia = (await h.ejecutar(ctx, h.validar({"destino": "PRINCIPAL"}))).para_modelo
    assert hacia["total"] == 4 and all(f["destino"] == "PRINCIPAL" for f in hacia["filas"])
    assert core_api.params() == {"sucursal": "PRINCIPAL"}                    # el Core API filtra por cualquiera de los dos
    desde = (await h.ejecutar(ctx, h.validar({"origen": "PRINCIPAL"}))).para_modelo
    assert desde["total"] == 1 and desde["filas"][0]["destino"] == "LA 21"
    todos = (await h.ejecutar(ctx, h.validar({}))).para_modelo
    assert todos["total"] >= 5 and "traslados en total" in todos["conteo"]


async def test_traslados_como_el_22oct(ctx, core_api):
    """Sin `catalogo`, el esquema y la salida del 22-oct: sucursal + dirección (y sin dirección, las dos)."""
    h = POR_NOMBRE["recomendar_traslados"]
    hacia = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL", "direccion": "hacia"}))).para_modelo
    assert hacia["total"] == 4 and all(f["destino"] == "PRINCIPAL" for f in hacia["filas"])
    assert hacia["filtro"] == {"sucursal": "PRINCIPAL", "direccion": "hacia", "por_tu_rol": False}
    desde = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL", "direccion": "desde"}))).para_modelo
    assert desde["total"] == 1 and desde["filas"][0]["destino"] == "LA 21"
    ambas = (await h.ejecutar(ctx, h.validar({"sucursal": "PRINCIPAL"}))).para_modelo
    assert ambas["total"] == 5 and core_api.params() == {"sucursal": "PRINCIPAL"}
    assert h.etiqueta(h.validar({"sucursal": "PRINCIPAL", "direccion": "hacia"})) == "Traslados sugeridos · hacia PRINCIPAL"


async def test_traslados_orden_y_llegada_tarde(ctx):
    h = POR_NOMBRE["recomendar_traslados"]
    r = (await h.ejecutar(ctx, h.validar({}))).para_modelo
    urgencias = [f["urgencia"] for f in r["filas"]]
    assert urgencias == sorted(urgencias, key=["urgente", "alta", "normal", "vigilancia"].index)
    assert r["filas"][0]["producto"].startswith("DURAZNO") and r["filas"][0]["llega_tarde"] is True   # 0 días: primero
    assert r["llegan_tarde"] == "1" and r["filas"][0]["cantidad"] == "13 unidades"
    assert h.lenta(h.validar({})) and h.etiqueta(h.validar({"destino": "PRINCIPAL", "urgencia": "urgente"})) \
        == "Traslados sugeridos · hacia PRINCIPAL · urgente"


async def test_traslados_permisos_del_rol(core_api, core):
    h = POR_NOMBRE["recomendar_traslados"]
    propia = (await h.ejecutar(_admin_la21(core), h.validar({"destino": "LA 21"}))).para_modelo
    assert propia["filtro"] == {"destino": "LA 21", "origen": None, "sucursal": "LA 21", "por_tu_rol": False}
    assert [f["destino"] for f in propia["filas"]] == ["LA 21"]
    with pytest.raises(ErrorHerramienta) as e:
        await h.ejecutar(_admin_la21(core), h.validar({"destino": "GLORIETA"}))
    assert e.value.status == 403


async def test_ventas_por_anio_de_un_producto(ctx, core_api, monkeypatch):
    """B4: con agrupación, el reporte de ventas del Core API, con valor y margen y el producto por su código."""
    monkeypatch.setattr(core_falso, "PRODUCTOS", core_falso.PRODUCTOS + [(626, "P626", "ARROZ DIANA *500 GR", "Arroz", "unidad")])
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "P626", "agrupacion": "anio"}))).para_modelo
    assert [f["periodo"] for f in r["filas"]] == ["2022", "2023", "2024", "2025"] and r["codigo"] == "P626"
    assert r["totales"]["cantidad"] == "42.434 unidades" and r["totales"]["valor"].startswith("$ ")
    assert core_api.params() == {"producto": "P626", "agrupacion": "anio", "fecha_inicio": "2000-01-01"}


async def test_ventas_ultimos_dias_sin_producto(ctx, core_api):
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(ctx, h.validar({"dias": 90}))).para_modelo
    assert r["agrupacion"] == "semana" and "nota" in r                     # sin producto: unidades y kilos mezclados
    assert core_api.params() == {"agrupacion": "semana", "fecha_inicio": "2025-10-03", "fecha_fin": "2025-12-31"}


async def test_ventas_sin_parametros_usa_30_dias_y_el_rol(core_api, core):
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(_admin_la21(core), h.validar({}))).para_modelo
    assert r["totales"]["cantidad"] == "21.714" and r["periodo"] == "2025-12-02 a 2025-12-31"
    with pytest.raises(ErrorHerramienta) as e:
        await h.ejecutar(_admin_la21(core), h.validar({"sucursal": "GLORIETA", "agrupacion": "mes"}))
    assert e.value.status == 403


async def test_ventas_con_producto_sin_agrupacion_sigue_igual(ctx, core_api):
    """Sin agrupación ni días: las ventanas de 15 días hábiles de INV-32, para comparar con el pronóstico."""
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "HUEVOS *UND", "sucursal": "PRINCIPAL"}))).para_modelo
    assert r["periodo"] == "15 días hábiles" and "/ventas" in core_api.peticiones[-1].url.path
    assert "/api/reportes/ventas" not in [p.url.path for p in core_api.peticiones]


async def test_traslados_de_un_producto(ctx):
    """Decisión del usuario (21-oct, v1-41): producto opcional, filtrado en el agente; si es ambiguo, se pregunta."""
    h = POR_NOMBRE["recomendar_traslados"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "HUEVOS *UND"}))).para_modelo
    assert [(f["producto"], f["origen"], f["destino"]) for f in r["filas"]] == [("HUEVOS *UND", "GLORIETA", "PRINCIPAL")]
    assert r["codigo"] == "P1632" and r["total"] == 1
    r = (await h.ejecutar(ctx, h.validar({"producto": "arroz carolina"}))).para_modelo
    assert r["resultado"] == "ambiguo"


def test_argumento_que_no_existe_se_rechaza():
    """Decisión del usuario (21-oct): antes se ignoraba y el modelo creía haber filtrado (v1-41)."""
    h = POR_NOMBRE["listar_alertas"]
    with pytest.raises(ErrorArgumentos, match="«producto» no existe en listar_alertas; válidos: "):
        h.validar({"producto": "Jabon Dersa", "sucursal": "PRINCIPAL"})
    assert h.validar({"producto": "", "sucursal": "PRINCIPAL"}).sucursal == "PRINCIPAL"     # vacío: se ignora, como antes


async def test_texto_en_varias_categorias_pide_aclarar(ctx, monkeypatch):
    """Z5 (C10): «arroz» está en Arroz y en Lácteos (ARROZ CON LECHE); con la categoría, no."""
    monkeypatch.setattr(core_falso, "INVENTARIO", core_falso.INVENTARIO + [(2372, 1, 10, 2, 5.0, "ok")])   # fila de prueba
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "arroz"}))).para_modelo
    assert r.get("aclarar") and {"Arroz", "Lácteos"} <= set(r["categorias"])
    r = (await h.ejecutar(ctx, h.validar({"producto": "arroz", "categoria": "Arroz"}))).para_modelo
    assert "aclarar" not in r
