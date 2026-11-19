"""INV-79: el pronóstico para una fecha elegida desde Vera, con el contrato de INV-62 (fecha_inicio y fecha_fin).
El agente resuelve las fechas en español con hoy en Bogotá y manda siempre fechas completas."""
import json
from datetime import date

import pytest

from herramientas import catalogo as cat
from herramientas.catalogo import POR_NOMBRE, resolver_fecha
from herramientas.core_api import ErrorHerramienta

HOY = date(2026, 11, 18)          # miércoles


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch):
    monkeypatch.setattr(cat, "hoy", lambda: HOY)


@pytest.mark.parametrize(("texto", "esperado"), [
    ("2026-12-15", (date(2026, 12, 15), None)),
    ("15/12/2026", (date(2026, 12, 15), None)),
    ("15/1", (date(2027, 1, 15), None)),                       # el enero más cercano a noviembre es el que viene
    ("15 de enero", (date(2027, 1, 15), None)),
    ("el 1 de octubre", (date(2026, 10, 1), None)),           # octubre ya pasó: el de este año
    ("1 de octubre de 2025", (date(2025, 10, 1), None)),
    ("mañana", (date(2026, 11, 19), None)),
    ("pasado mañana", (date(2026, 11, 20), None)),
    ("el viernes", (date(2026, 11, 20), None)),
    ("el miércoles", (date(2026, 11, 25), None)),              # hoy es miércoles: el de la semana que viene
    ("la próxima semana", (date(2026, 11, 23), date(2026, 11, 29))),
    ("esta semana", (date(2026, 11, 18), date(2026, 11, 22))),
    ("el próximo mes", (date(2026, 12, 1), date(2026, 12, 31))),
    ("diciembre", (date(2026, 12, 1), date(2026, 12, 31))),
    ("enero de 2027", (date(2027, 1, 1), date(2027, 1, 31))),
    ("fin de mes", (date(2026, 11, 30), None)),
])
def test_resolver_fecha(texto, esperado):
    assert resolver_fecha(texto, HOY) == esperado


@pytest.mark.parametrize("texto", ["31 de febrero de 2026", "el día de la madre", "2026-13-01"])
def test_fechas_que_no_se_entienden(texto):
    with pytest.raises(ErrorHerramienta) as e:
        resolver_fecha(texto, HOY)
    assert e.value.status == 422


def _ultimo_cuerpo(core_api):
    return json.loads([p for p in core_api.peticiones if p.url.path == "/api/ml/predict"][-1].content)


async def test_desde_una_fecha_pasada_se_compara_con_lo_vendido(ctx, core_api):
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "1 de diciembre de 2025"}))
    assert _ultimo_cuerpo(core_api) == {"producto_id": "P1632", "sucursal_id": "GLORIETA", "horizonte": 15,
                                        "fecha_inicio": "2025-12-01"}
    m = r.para_modelo
    assert m["tipo"].startswith("pasado") and m["consulta"] == {"desde": "2025-12-01", "hasta": None}
    assert m["filas"][0]["vendido"] == "3.484 unidades" and m["filas"][0]["diferencia"] == "+11,1 % sobre lo vendido"
    assert [t["etiqueta"] for t in r.data["tarjetas"]] == ["Demanda de la ventana", "Vendido en la ventana", "Diferencia",
                                                           "Datos hasta"]
    assert r.data["grafico"]["series"][1]["clave"] == "vendido"


async def test_un_dia_futuro_es_un_reparto_aproximado(ctx, core_api):
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "15 de enero",
                                         "hasta": "15 de enero"}))
    assert _ultimo_cuerpo(core_api)["fecha_inicio"] == "2027-01-15" and _ultimo_cuerpo(core_api)["fecha_fin"] == "2027-01-15"
    m = r.para_modelo
    assert m["tipo"] == "futuro" and m["filas"][0]["rango_aproximado"] == "258 unidades" and m["filas"][0]["metodo"] == "reparto"
    assert "vendido" not in m["filas"][0] and "aproximación" in m["nota"]
    assert r.data["tarjetas"][0]["etiqueta"] == "Pronóstico del rango" and "aproximado" in r.data["tarjetas"][0]["detalle"]


async def test_un_rango_largo_encadena_ventanas(ctx, core_api):
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "2025-10-01",
                                         "hasta": "2025-11-29"}))
    m = r.para_modelo
    assert m["filas"][0]["metodo"] == "ventanas_encadenadas" and m["filas"][0]["dias_habiles"] == 60
    g = r.data["grafico"]
    assert g["x"] == "hasta" and len(g["datos"]) == 4 and [s["clave"] for s in g["series"]] == ["pronostico", "vendido"]
    assert r.data["titulo"] == "Pronóstico · HUEVOS *UND · GLORIETA · 1 oct a 29 nov 2025"


async def test_un_periodo_con_nombre_trae_su_fin(ctx, core_api):
    h = POR_NOMBRE["pronosticar_demanda"]
    await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "la próxima semana"}))
    assert {k: _ultimo_cuerpo(core_api)[k] for k in ("fecha_inicio", "fecha_fin")} == {"fecha_inicio": "2026-11-23",
                                                                                      "fecha_fin": "2026-11-29"}


async def test_varias_sucursales_con_fecha(ctx):
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "desde": "mañana", "hasta": "mañana"}))
    assert r.para_modelo["total"] == 3 and r.data["grafico"]["x"] == "sucursal" and len(r.data["grafico"]["datos"]) == 3


async def test_errores(ctx):
    h = POR_NOMBRE["pronosticar_demanda"]
    with pytest.raises(ErrorHerramienta, match="antes de empezar"):
        await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "15 de diciembre",
                                         "hasta": "1 de diciembre"}))
    with pytest.raises(ErrorHerramienta) as e:          # el Core API rechaza un rango de más de 90 días hábiles
        await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "2026-01-01",
                                         "hasta": "2026-12-31"}))
    assert e.value.status == 422
    assert h.etiqueta(h.validar({"producto": "x", "sucursal": "GLORIETA", "desde": "mañana"})) == \
        "Pronóstico de demanda · GLORIETA · mañana"


async def test_sin_fecha_todo_sigue_igual(ctx, core_api):
    h = POR_NOMBRE["pronosticar_demanda"]
    await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA"}))
    assert _ultimo_cuerpo(core_api) == {"producto_id": "P1632", "sucursal_id": "GLORIETA", "horizonte": 15}


async def test_rango_con_parte_fuera_de_lo_medido(ctx, core_api, monkeypatch):
    """INV-62: diciembre completo con los datos al 30-sep tiene su última ventana a más de 90 días hábiles."""
    from tests import core_falso
    original = core_falso._prediccion_con_fecha

    def con_fuera(*args):
        r = original(*args)
        cuerpo = json.loads(r.content)
        cuerpo["rango"]["fuera_de_lo_medido"] = True
        return core_falso.httpx.Response(200, json=cuerpo)
    monkeypatch.setattr(core_falso, "_prediccion_con_fecha", con_fuera)
    h = POR_NOMBRE["pronosticar_demanda"]
    r = await h.ejecutar(ctx, h.validar({"producto": "huevos", "sucursal": "GLORIETA", "desde": "diciembre"}))
    assert "fuera de lo medido" in r.para_modelo["nota_rango"]
    assert r.data["tarjetas"][0]["tono"] == "atencion" and "fuera de lo medido" in r.data["tarjetas"][0]["detalle"]
