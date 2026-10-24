"""Búsqueda tolerante (INV-33, brecha B1): abreviaturas de la bodega, palabras en cualquier orden, el caso
«PAPA * KL» y el código de producto en el inventario. Los nombres son reales de la bodega."""
import json

import pytest

from herramientas import contexto
from herramientas.catalogo import POR_NOMBRE
from herramientas.contexto import (
    ARCHIVO_ABREVIATURAS,
    abreviaturas_de,
    aclaracion_abreviatura,
    cargar_abreviaturas,
    contiene_todas,
    requiere_busqueda_por_palabras,
)
from tests import core_falso

# Productos de dw.dim_producto (nombres y códigos reales; los id y el código de RAPI PAPA son de prueba) que se
# agregan al Core API simulado
EXTRA = [(632, "P1350", "CHOC SOL *750GR", "Chocolate", "unidad"), (285, "P285", "JAB DERSA AZUL PURO *230GR", "Aseo hogar", "unidad"),
         (289, "P289", "JAB DERSA COCO *200GR", "Aseo hogar", "unidad"),
         (2866, "02866", "JABON DERSA LAVANDA / LIMON *220 GR", "Frutas y verduras", "unidad"),
         (7002, "P1810", "PAPA CRIOLLA *KL", "Frutas y verduras", "kg"), (7003, "P9910", "RAPI PAPA * KL", "Frutas y verduras", "kg"),
         (1234, "P1234", "PONQUE BIMBO CASERO *240GR", "Panadería", "unidad")]
INV_EXTRA = [(632, 1, 26, 1, 60.7, "ok"), (7002, 2, 12, 3, 4.0, "bajo"), (7003, 2, 5, 1, 50.5, "ok"), (7001, 2, 8, 2, 3.5, "bajo"),
             (1234, 3, 3, 1, 10.0, "ok")]


@pytest.fixture
def abreviaturas(monkeypatch):
    monkeypatch.setattr(contexto, "ABREVIATURAS", {"jabon": ("jab",), "chocolate": ("choc",), "galleta": ("gall",),
                                                    "aceite": ("ac",)})


@pytest.fixture
def bodega(monkeypatch):
    monkeypatch.setattr(core_falso, "PRODUCTOS", core_falso.PRODUCTOS + EXTRA)
    monkeypatch.setattr(core_falso, "INVENTARIO", core_falso.INVENTARIO + INV_EXTRA)


def test_abreviaturas_y_plurales(abreviaturas):
    assert abreviaturas_de("chocolate") == ("choc",) and abreviaturas_de("galletas") == ("gall",)
    assert abreviaturas_de("arroz") == ()
    assert contiene_todas("CHOC SOL *750GR", ["chocolate", "sol", "750"])
    assert contiene_todas("AC DIANA PREMIUN *900ML", ["aceite", "diana"])
    assert not contiene_todas("ACADEMIA DEL SABOR", ["aceite"])            # la abreviatura cuenta solo como palabra
    assert not contiene_todas("CHOC SOL *750GR", ["chocolate", "sol", "75"])   # los números, completos


def test_sin_diccionario_la_busqueda_es_la_de_antes(monkeypatch):
    monkeypatch.setattr(contexto, "ABREVIATURAS", {})
    assert not contiene_todas("CHOC SOL *750GR", ["chocolate", "sol"])


def test_cuando_hace_falta_buscar_por_palabras(abreviaturas):
    assert requiere_busqueda_por_palabras("chocolate sol", ["CHOCOLATE SOL"])        # «chocolate» tiene abreviatura
    assert requiere_busqueda_por_palabras("PAPA * KL", ["RAPI PAPA * KL"])           # no empieza por «papa»
    assert requiere_busqueda_por_palabras("arroz", [])                               # no encontró nada
    assert not requiere_busqueda_por_palabras("arroz carolina", ["ARROZ CAROLINA *500 GR"])
    assert not requiere_busqueda_por_palabras("de la", [])                           # sin palabras útiles


def test_el_archivo_del_diccionario(tmp_path):
    ruta = tmp_path / "abreviaturas.json"
    ruta.write_text(json.dumps({"abreviaturas": {"Jabón": ["JAB"], "Café": ["CAF"], "champú / shampoo": ["CHAMP"]}}),
                    encoding="utf-8")
    assert cargar_abreviaturas(ruta) == {"jabon": ("jab",), "cafe": ("caf",), "champu": ("champ",), "shampoo": ("champ",)}
    assert cargar_abreviaturas(tmp_path / "no-existe.json") == {}


async def test_buscar_producto_con_abreviaturas(ctx, core_api, abreviaturas, bodega):
    h = POR_NOMBRE["buscar_producto"]
    r = (await h.ejecutar(ctx, h.validar({"texto": "chocolate sol 750"}))).para_modelo
    assert [f["nombre"] for f in r["filas"]] == ["CHOC SOL *750GR"]
    r = (await h.ejecutar(ctx, h.validar({"texto": "Jabon Dersa"}))).para_modelo
    assert {f["nombre"] for f in r["filas"]} == {"JABON DERSA LAVANDA / LIMON *220 GR", "JAB DERSA AZUL PURO *230GR",
                                                 "JAB DERSA COCO *200GR"}
    assert "jab" in [p.get("busqueda") for p in (core_api.params(i) for i in range(len(core_api.peticiones)))]


async def test_inventario_papa_kl_y_codigo(ctx, core_api, bodega):
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "PAPA * KL", "sucursal": "LA 21"}))).para_modelo
    assert {f["producto"] for f in r["filas"]} >= {"RAPI PAPA * KL", "PAPA CRIOLLA *KL", "PAPA PASTUSA *KL"}
    r = (await h.ejecutar(ctx, h.validar({"producto": "P1234", "sucursal": "GLORIETA"}))).para_modelo
    assert [f["producto"] for f in r["filas"]] == ["PONQUE BIMBO CASERO *240GR"] and r["total"] == 1


async def test_inventario_con_abreviatura(ctx, abreviaturas, bodega):
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "Chocolate Sol * 750"}))).para_modelo
    assert [f["producto"] for f in r["filas"]] == ["CHOC SOL *750GR"]


async def test_nombre_exacto_no_cambia(ctx, core_api, bodega):
    """Un nombre que ya se encuentra entero no dispara la búsqueda por palabras."""
    h = POR_NOMBRE["consultar_inventario"]
    antes = len(core_api.peticiones)
    r = (await h.ejecutar(ctx, h.validar({"producto": "HUEVOS *UND", "sucursal": "GLORIETA"}))).para_modelo
    assert [f["producto"] for f in r["filas"]] == ["HUEVOS *UND"]
    assert sum(p.url.path == "/api/consulta/inventario" for p in core_api.peticiones[antes:]) == 1


def test_el_diccionario_validado():
    """Las 30 entradas que validó el usuario el 21-oct (Descargas/INV-33-diccionario-abreviaturas.xlsx)."""
    d = json.loads(ARCHIVO_ABREVIATURAS.read_text(encoding="utf-8"))["abreviaturas"]
    assert len(d) == 30 and d["jabón"] == ["JAB"] and d["acondicionador"] == d["aceite"] == ["AC"]
    assert cargar_abreviaturas()["galletas"] == ("gall",)


@pytest.fixture
def ac_compartida(monkeypatch):
    monkeypatch.setattr(contexto, "ABREVIATURAS", {"aceite": ("ac",), "acondicionador": ("ac",), "champu": ("champ",),
                                                    "shampoo": ("champ",), "jabon": ("jab",)})
    monkeypatch.setattr(contexto, "SINONIMOS", {"champu": frozenset({"champu", "shampoo"}),
                                                 "shampoo": frozenset({"champu", "shampoo"})})


def test_abreviatura_de_dos_palabras_pide_aclarar(ac_compartida):
    """Regla del usuario (21-oct): AC es aceite y acondicionador; con categorías distintas, se pregunta."""
    r = aclaracion_abreviatura("acondicionador", ["Cuidado personal", "Aceites y sustitutos", "Cuidado personal"])
    assert r["aclarar"] and r["categorias"] == ["Aceites y sustitutos", "Cuidado personal"] and "«aceite»" in r["indicacion"]
    assert aclaracion_abreviatura("aceites", ["Cuidado personal", "Aceites y sustitutos"])["aclarar"]
    assert aclaracion_abreviatura("acondicionador", ["Cuidado personal"]) is None          # una sola categoría
    assert aclaracion_abreviatura("jabon", ["Aseo hogar", "Cuidado personal"]) is None     # JAB es solo jabón
    assert aclaracion_abreviatura("shampoo", ["Cuidado personal", "Bebé"]) is None         # sinónimos, no dudosa


async def test_buscar_acondicionador_pide_aclarar(ctx, ac_compartida, monkeypatch):
    extra = [(1034, "02210", "AC DIANA  * 450ML", "Aceites y sustitutos", "unidad"),
             (5001, "P5001", "ACONDICIONADOR SAVITAL *490", "Cuidado personal", "unidad")]   # ids de prueba
    monkeypatch.setattr(core_falso, "PRODUCTOS", core_falso.PRODUCTOS + extra)
    h = POR_NOMBRE["buscar_producto"]
    r = (await h.ejecutar(ctx, h.validar({"texto": "acondicionador"}))).para_modelo
    assert r["aclarar"] and r["total"] == 2
    r = (await h.ejecutar(ctx, h.validar({"texto": "acondicionador savital"}))).para_modelo
    assert "aclarar" not in r and [f["nombre"] for f in r["filas"]] == ["ACONDICIONADOR SAVITAL *490"]
