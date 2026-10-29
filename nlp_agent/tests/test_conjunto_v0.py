"""Conjunto v0 del spike: esquema, cobertura que pide la ficha y variante sin datos reales para Colab."""
import json

import pytest

from evaluacion import catalogo_v0
from evaluacion.conjunto import (
    FECHA_COLAB,
    Esperado,
    Pregunta,
    cargar,
    coincide,
    errores_contra_catalogo,
    herramientas,
    resultado_para,
)


@pytest.fixture(scope="module", params=["local", "colab"])
def variante(request):
    return request.param, cargar(request.param), herramientas(request.param)


def test_validas_contra_el_catalogo(variante):
    _, conjunto, catalogo = variante
    assert errores_contra_catalogo(conjunto, catalogo) == []


def test_cobertura_de_la_ficha():
    """INV-31, criterio 6: 20 preguntas base y sus variantes, al menos 10 % de abstención, los 3 roles, cada herramienta."""
    c = cargar()
    base = [p for p in c.preguntas if p.variante_de is None]
    assert (len(base), len(c.preguntas)) == (20, 43)
    assert len({p.id for p in c.preguntas}) == 43
    assert sum(p.abstencion for p in base) >= 4
    assert sum(p.abstencion for p in c.preguntas) >= 0.1 * len(c.preguntas)
    assert {p.rol for p in c.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert sum(p.tipo == "adversarial" for p in c.preguntas) >= 2
    usadas = {e.herramienta for p in c.preguntas for e in p.esperado}
    assert usadas == catalogo_v0.nombres()


def test_cada_herramienta_esperada_tiene_resultado():
    for p in cargar().preguntas:
        for e in p.esperado:
            assert e.herramienta in p.resultados, (p.id, e.herramienta)


def test_la_variante_de_colab_no_lleva_sucursales_ni_fecha_reales():
    """Sin distinguir mayúsculas: los usuarios escriben «glorieta» o «almacen principal»."""
    import re
    datos = cargar("colab").model_dump()
    # «tipo»: «principal» es el tipo de sucursal, no su nombre
    for p in datos["preguntas"]:
        for r in p["resultados"].values():
            for fila in (r.get("filas", []) if isinstance(r, dict) else []):
                fila.pop("tipo", None)
    texto = json.dumps(datos, ensure_ascii=False) + json.dumps(herramientas("colab"), ensure_ascii=False)
    assert re.findall(r"(?i)principal|glorieta|la 21|2025-12-31", texto) == []
    assert cargar("colab").fecha_datos == FECHA_COLAB
    assert "{fecha}" not in texto


def test_la_variante_local_resuelve_la_fecha():
    c = cargar()
    assert c.por_id("v0-01").resultados["consultar_inventario"]["fecha_dato"] == "2025-12-31"


def test_catalogo_detecta_errores():
    c = cargar()
    c.preguntas[0].esperado[0].herramienta = "borrar_todo"
    c.preguntas[1].esperado[0].argumentos["estado"] = "rojo"
    c.preguntas[2].esperado[0].argumentos["color"] = "azul"
    c.preguntas[3].resultados["inventada"] = {}
    errores = errores_contra_catalogo(c, catalogo_v0.herramientas())
    assert len(errores) == 4


@pytest.mark.parametrize("cambio", [
    {"abstencion": True},                                   # abstención con llamadas esperadas
    {"esperado": []},                                       # sin llamadas y sin abstención
    {"sucursal_usuario": "LA 21"},                          # un gerente con sucursal
])
def test_esquema_rechaza_preguntas_incoherentes(cambio):
    base = cargar().por_id("v0-01").model_dump()
    with pytest.raises(ValueError):
        Pregunta(**{**base, **cambio})


@pytest.mark.parametrize("herramienta,argumentos,vale", [
    ("consultar_inventario", {"sucursal": "Glorieta", "producto": "Huevos"}, True),     # mayúsculas
    ("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevo"}, True),
    ("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos", "categoria": ""}, True),  # vacío = ausente
    ("consultar_inventario", {"sucursal": "GLORIETA"}, False),                           # falta el producto
    ("consultar_inventario", {"sucursal": "PRINCIPAL", "producto": "huevos"}, False),    # otra sucursal
    ("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos", "estado": "critico"}, False),  # inventado
    ("buscar_producto", {"sucursal": "GLORIETA", "producto": "huevos"}, False),          # otra herramienta
])
def test_regla_de_argumentos(herramienta, argumentos, vale):
    esperado = Esperado(herramienta="consultar_inventario", argumentos={"sucursal": "GLORIETA", "producto": {"contiene": "huevo"}})
    assert coincide(esperado, herramienta, argumentos) is vale


def test_opcionales_y_comodin():
    e = Esperado(herramienta="listar_alertas", argumentos={"sucursal": "GLORIETA"}, opcionales={"origen": "ia", "urgencia": "*"})
    assert coincide(e, "listar_alertas", {"sucursal": "GLORIETA", "origen": "IA", "urgencia": "alta"})
    assert not coincide(e, "listar_alertas", {"sucursal": "GLORIETA", "origen": "reglas"})


def test_las_compras_de_v0_10_y_v0_11_no_aceptan_filtros_inventados():
    c = cargar()
    assert not coincide(c.por_id("v0-10").esperado[0], "recomendar_compras", {"sucursal": "BODEGA_CENTRAL", "urgencia": "urgente", "categoria": "todos"})
    assert not coincide(c.por_id("v0-11").esperado[0], "recomendar_compras", {"sucursal": "GLORIETA", "categoria": "Lácteos", "urgencia": "normal"})


def test_variantes_conservan_rol_y_apuntan_a_una_base():
    c = cargar()
    for p in c.preguntas:
        if p.variante_de:
            base = c.por_id(p.variante_de)
            assert base.variante_de is None and (p.rol, p.sucursal_usuario) == (base.rol, base.sucursal_usuario), p.id


def test_resultados_segun_los_argumentos():
    c = cargar()
    arroz = c.por_id("v0-09b")
    assert resultado_para(arroz, "pronosticar_demanda", {"producto": "carolina", "sucursal": "la 21"}, "x")["demanda_esperada"] == "410 unidades"
    assert resultado_para(arroz, "pronosticar_demanda", {"producto": "carolina"}, "x")["error"]["status"] == 422
    bodega = c.por_id("v0-06b")
    assert resultado_para(bodega, "listar_alertas", {"sucursal": "BODEGA_CENTRAL", "origen": "ia"}, "x")["total"] == 0
    assert resultado_para(bodega, "listar_alertas", {"sucursal": "BODEGA_CENTRAL"}, "x")["total"] == 412
    vacio = resultado_para(bodega, "recomendar_compras", {}, "2025-12-31")
    assert vacio == {"fecha_dato": "2025-12-31", "total": 0, "filas": []}


def test_condicion_de_argumento_ausente():
    from evaluacion.conjunto import Pregunta
    p = Pregunta(id="x", rol="gerente", sucursal_usuario=None, tipo="herramienta", pregunta="¿qué?",
                 esperado=[{"herramienta": "consultar_inventario"}],
                 resultados={"consultar_inventario": [{"si": {"sucursal": None}, "resultado": {"todas": True}},
                                                      {"resultado": {"todas": False}}]})
    assert resultado_para(p, "consultar_inventario", {}, "x") == {"todas": True}
    assert resultado_para(p, "consultar_inventario", {"sucursal": "LA 21"}, "x") == {"todas": False}


def test_filtra_las_filas_por_la_sucursal_pedida():
    c = cargar()
    huevos = c.por_id("v0-01b")
    todas = resultado_para(huevos, "consultar_inventario", {"producto": "huevos"}, "x")
    assert todas["total"] == 4
    bodega = resultado_para(huevos, "consultar_inventario", {"producto": "huevos", "sucursal": "BODEGA_CENTRAL"}, "x")
    assert (bodega["total"], bodega["filas"][0]["stock"]) == (1, "0 unidades")
    otra = resultado_para(c.por_id("v0-01"), "consultar_inventario", {"producto": "huevos", "sucursal": "PRINCIPAL"}, "x")
    assert (otra["total"], otra["filas"]) == (0, [])
    alertas = resultado_para(c.por_id("v0-05"), "resumen_alertas", {"sucursal": "LA 21"}, "x")
    assert [f["sucursal"] for f in alertas["filas"]] == ["LA 21"]
    # Sin campo sucursal en las filas (un listado de productos), no se filtra
    assert resultado_para(c.por_id("v0-02"), "consultar_inventario", {"sucursal": "PRINCIPAL"}, "x")["total"] == 23


@pytest.mark.parametrize("id_,esperada", [
    ("v0-02b", "Tenemos estado crítico para productos lacteos en centro?"),
    ("v0-04b", "Reporte venta de huevos en Centro el mes pasado"),
    ("v0-07b", "Pronóstica con IA los productos proximos a agotarse en sur"),
    ("v0-11b", "Sugerido de pedido de lácteos para Sur"),
    ("v0-19", "¿Cuántos huevos hay en CENTRO?"),
])
def test_colab_conserva_el_estilo_de_cada_pregunta(id_, esperada):
    assert cargar("colab").por_id(id_).pregunta == esperada


def test_colab_no_cambia_el_tipo_de_sucursal():
    filas = cargar("colab").por_id("v0-12").resultados["listar_sucursales"]["filas"]
    assert [(f["nombre"], f["tipo"]) for f in filas][:2] == [("CENTRO", "principal"), ("NORTE", "estándar")]


def test_colab_solo_reemplaza_palabras_completas():
    from evaluacion.conjunto import _texto_colab
    assert _texto_colab("principalmente en la Glorieta y LA 21") == "principalmente en la Sur y NORTE"
