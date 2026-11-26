"""INV-40, ampliación del 18-nov: tarjetas y gráficas en el evento `data` (contrato v1.2), la ficha de producto,
precios y márgenes, y el pronóstico al día presente (punto 1.3 de la hoja de ruta)."""
from datetime import UTC, date

import pytest

from herramientas import catalogo as cat
from herramientas.base import grafico, tabla, tarjeta
from herramientas.catalogo import POR_NOMBRE, al_dia, ventana_habil, viernes_santo
from herramientas.core_api import ErrorHerramienta
from tests.test_brechas_catalogo import _admin_la21


@pytest.fixture
def hoy_fijo(monkeypatch):
    def fijar(dia: date):
        monkeypatch.setattr(cat, "hoy", lambda: dia)
    return fijar


def test_contrato_v12_opcional():
    vacia = tabla("T", [], [], 0)
    assert "tarjetas" not in vacia and "grafico" not in vacia                 # un cliente viejo no ve nada nuevo
    g = grafico("barras", "x", [("v", "Valor")], [{"x": "a", "v": 1.5, "otra": 9}], "$")
    assert g == {"tipo": "barras", "x": "x", "series": [{"clave": "v", "etiqueta": "Valor"}], "datos": [{"x": "a", "v": 1.5}],
                 "unidad": "$"}
    assert "grafico" not in tabla("T", [], [], 0, grafico=grafico("linea", "x", [("v", "V")], []))   # sin datos, sin gráfica
    with pytest.raises(ValueError):
        tarjeta("A", "1", tono="rojo")
    with pytest.raises(ValueError):
        grafico("torta", "x", [], [{"x": 1}])


def test_viernes_santo_y_ventana():
    assert viernes_santo(2026) == date(2026, 4, 3) and viernes_santo(2025) == date(2025, 4, 18)
    assert ventana_habil("2025-12-31") == (date(2026, 1, 2), date(2026, 1, 16))      # el 1 de enero no cuenta
    assert ventana_habil("2026-03-31") == (date(2026, 4, 1), date(2026, 4, 16))      # ni el Viernes Santo


def test_al_dia_con_el_servicio_anterior(hoy_fijo):
    hoy_fijo(date(2026, 11, 18))
    dia = al_dia("2026-09-30")
    assert dia["ventana"] == {"desde": "2026-10-01", "hasta": "2026-10-15"} and not dia["hoy_en_ventana"]
    assert "cargar las ventas y el inventario hasta hoy" in dia["nota_hoy"]
    hoy_fijo(date(2026, 10, 7))
    assert al_dia("2026-09-30")["hoy_en_ventana"] and "nota_hoy" not in al_dia("2026-09-30")


def test_al_dia_con_el_contrato_de_inv62(hoy_fijo):
    """INV-62: la ventana parte de la fecha de operación (hoy) y la respuesta trae los días sin datos."""
    hoy_fijo(date(2026, 11, 18))
    r = {"fecha_features": "2026-09-30", "fecha_datos": "2026-09-30", "fecha_operacion": "2026-11-18",
         "ventana_desde": "2026-11-19", "ventana_hasta": "2026-12-03", "dias_habiles_sin_datos": 49}
    dia = al_dia("2026-09-30", r)
    assert dia["ventana"] == {"desde": "2026-11-19", "hasta": "2026-12-03"} and dia["fecha_operacion"] == "2026-11-18"
    assert "49 días hábiles sin datos" in dia["nota_datos"] and "nota_hoy" not in dia
    assert dia["hoy_en_ventana"] is True                 # parte de hoy aunque la ventana empiece mañana


async def test_pronostico_con_ventana_por_dia_y_tarjetas(ctx, hoy_fijo):
    hoy_fijo(date(2026, 1, 5))
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA"}))
    m = r.para_modelo
    assert m["ventana"] == {"desde": "2026-01-02", "hasta": "2026-01-16"} and m["hoy_en_ventana"] is True
    assert m["por_dia_habil"] == "258 unidades"                                    # 3.871,25 ÷ 15
    assert [t["etiqueta"] for t in r.data["tarjetas"]] == ["Demanda esperada", "Por día hábil", "Límite de negocio", "Ventana",
                                                           "Mismo periodo del año pasado"]
    varias = await h.ejecutar(ctx, h.validar({"producto": "huevos"}))
    assert varias.data["grafico"]["tipo"] == "barras" and len(varias.data["grafico"]["datos"]) == 3


async def test_ventas_y_ranking_con_tarjetas_y_grafica(ctx):
    h = POR_NOMBRE["historial_ventas"]
    # INV-72: por mes sin días va al análisis; sin producto, las unidades no se suman (sin tarjeta de cantidad)
    r = await h.ejecutar(ctx, h.validar({"agrupacion": "mes"}))
    assert [t["etiqueta"] for t in r.data["tarjetas"]] == ["Ventas", "Margen"]
    assert r.data["grafico"]["tipo"] == "barras" and r.data["grafico"]["datos"][0]["valor"] == 1000.0
    ventanas = await h.ejecutar(ctx, h.validar({"producto": "huevos"}))
    assert ventanas.data["grafico"]["series"][0]["clave"] in ("PRINCIPAL", "LA 21", "GLORIETA")
    top = await POR_NOMBRE["productos_mas_vendidos"].ejecutar(ctx, POR_NOMBRE["productos_mas_vendidos"].validar({}))
    assert top.data["grafico"]["tipo"] == "barras_h" and len(top.data["grafico"]["datos"]) == 10


async def test_resumenes_con_tarjetas_y_apiladas(ctx):
    inv = await POR_NOMBRE["resumen_inventario"].ejecutar(ctx, POR_NOMBRE["resumen_inventario"].validar({}))
    assert [t["etiqueta"] for t in inv.data["tarjetas"]][-1] == "En riesgo" and inv.data["grafico"]["tipo"] == "apiladas"
    una = await POR_NOMBRE["resumen_inventario"].ejecutar(ctx, POR_NOMBRE["resumen_inventario"].validar({"sucursal": "GLORIETA"}))
    assert "grafico" not in una.data and una.data["tarjetas"]                     # una sucursal: sin apilar
    al = await POR_NOMBRE["resumen_alertas"].ejecutar(ctx, POR_NOMBRE["resumen_alertas"].validar({}))
    assert [t["tono"] for t in al.data["tarjetas"]][:2] == ["critico", "atencion"]


async def test_ficha_de_producto(ctx, hoy_fijo):
    hoy_fijo(date(2026, 11, 18))
    h = POR_NOMBRE["ficha_producto"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos"}))
    m = r.para_modelo
    assert m["catalogo"]["precio"] == "$ 1.091" and m["catalogo"]["margen"] == "25,0 %" and m["catalogo"]["proveedores"]
    assert m["ventas_30_dias"]["periodo"] == "2025-12-02 a 2025-12-31" and m["pronostico"]["horizonte"] == "15 días hábiles"
    assert "nota_hoy" in m["pronostico"] and {f["ubicacion"] for f in m["filas"]} >= {"GLORIETA", "PRINCIPAL"}
    assert len(r.data["tarjetas"]) == 6 and r.data["grafico"]["series"][1]["clave"] == "demanda"
    assert h.lenta(h.validar({"producto": "x"})) and h.etiqueta(h.validar({"producto": "huevos"})) == "Ficha de producto · huevos"
    ambiguo = await h.ejecutar(ctx, h.validar({"producto": "arroz carolina"}))
    assert ambiguo.data is None and ambiguo.para_modelo["resultado"] == "ambiguo"


async def test_ficha_con_los_permisos_del_rol(core):
    h = POR_NOMBRE["ficha_producto"]
    m = (await h.ejecutar(_admin_la21(core), h.validar({"producto": "huevos"}))).para_modelo
    assert {f["ubicacion"] for f in m["filas"]} <= {"LA 21", "BODEGA_CENTRAL"}       # lo que ve en el inventario


async def test_precios_de_un_producto(ctx):
    h = POR_NOMBRE["precios_y_margenes"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "periodo": "diciembre"}))
    m = r.para_modelo
    assert m["catalogo"]["costo"] == "$ 818" and m["margen_realizado"]["periodo"] == "2025-12-01 a 2025-12-31"
    assert m["margen_realizado"]["margen_pct"] == "20,0 %" and "última venta registrada" in m["nota"]
    assert [t["etiqueta"] for t in r.data["tarjetas"]] == ["Precio", "Costo", "Margen de catálogo", "Ventas del periodo",
                                                           "Margen realizado"]
    with pytest.raises(ErrorHerramienta, match="producto o una categoría"):
        await h.ejecutar(ctx, h.validar({}))


async def test_reporte_de_una_categoria_desglosado(ctx, core_api):
    h = POR_NOMBRE["precios_y_margenes"]
    r = await h.ejecutar(ctx, h.validar({"categoria": "arroz"}))
    m = r.para_modelo
    assert m["categoria"] == "Arroz" and m["mostrando"] <= 10 and len(r.data["filas"]) == m["total"]
    assert all(f["precio"].startswith("$ ") for f in r.data["filas"]) and r.data["grafico"]["tipo"] == "barras_h"
    assert m["totales_de_los_productos"]["margen_pct"] == "20,0 %"
    top = [p for p in core_api.peticiones if p.url.path == "/api/reportes/ventas/top-productos"][-1]
    assert dict(top.url.params)["limite"] == "50" and dict(top.url.params)["categoria"] == "Arroz"


def test_periodos_relativos_y_fuera_de_lo_medido(hoy_fijo):
    from herramientas.catalogo import normalizar_periodo
    assert normalizar_periodo("mes pasado", date(2025, 12, 31)) == "2025-11"
    assert normalizar_periodo("el mes pasado", date(2026, 1, 15)) == "2025-12"
    assert normalizar_periodo("este mes", date(2026, 9, 30)) == "2026-09"
    assert normalizar_periodo("año pasado", date(2026, 9, 30)) == "2025"
    assert normalizar_periodo("este año", date(2026, 9, 30)) == "2026"
    hoy_fijo(date(2027, 1, 15))
    dia = al_dia("2026-09-30", {"fecha_operacion": "2027-01-15", "ventana_desde": "2027-01-16", "ventana_hasta": "2027-01-30",
                                "dias_habiles_sin_datos": 106, "fuera_de_lo_medido": True})
    assert dia["fuera_de_lo_medido"] and "Cargue" not in dia["nota_fuera_de_lo_medido"]
    assert "fuera de lo medido" in dia["nota_fuera_de_lo_medido"] and "106 días hábiles sin datos" in dia["nota_datos"]
    assert "fuera_de_lo_medido" not in al_dia("2026-09-30", {"fuera_de_lo_medido": False})


async def test_historial_del_mes_pasado(ctx, core_api):
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(ctx, h.validar({"periodo": "mes pasado"}))).para_modelo
    assert r["periodo"] == "2025-11-01 a 2025-11-30"


def test_hoy_es_la_fecha_de_bogota(monkeypatch):
    """A las 9 de la noche en Bogotá ya es el día siguiente en UTC; la fecha de hoy debe ser la de Bogotá."""
    from datetime import datetime
    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 19, 2, 0, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(cat, "datetime", Reloj)
    assert cat.hoy() == date(2026, 11, 18)
