"""
Prueba de contrato (INV-32, criterio 7, T13): las herramientas contra el OpenAPI
versionado del Core API (api/tests/postman/inventaio-core-api.openapi.yml).

Falla si el Core API cambia una ruta, un parámetro, un enum o un campo de la
respuesta que lee una herramienta y el OpenAPI se regenera sin cambiar el
catálogo. El OpenAPI vive en el mismo repositorio, así que corre en el CI.
"""
from pathlib import Path

import pytest
import yaml

from herramientas.catalogo import (
    CATALOGO,
    ENDPOINTS_CONTEXTO,
    POR_NOMBRE,
    TIPOS_IA,
    TIPOS_REGLAS,
)

OPENAPI = yaml.safe_load((Path(__file__).resolve().parents[2] / "api/tests/postman/inventaio-core-api.openapi.yml")
                         .read_text(encoding="utf-8"))
ENDPOINTS = sorted({e for h in CATALOGO for e in h.endpoints} | set(ENDPOINTS_CONTEXTO))


def _resolver(esquema: dict) -> dict:
    while "$ref" in esquema:
        esquema = OPENAPI["components"]["schemas"][esquema["$ref"].split("/")[-1]]
    return esquema


def _operacion(metodo: str, ruta: str) -> dict:
    return OPENAPI["paths"][ruta][metodo.lower()]


def _parametro(metodo: str, ruta: str, nombre: str) -> dict:
    return next(p for p in _operacion(metodo, ruta).get("parameters", []) if p["name"] == nombre)


def _enum(esquema: dict) -> set:
    valores = set(esquema.get("enum", []))
    for sub in esquema.get("anyOf", []) + ([esquema["items"]] if "items" in esquema else []):
        valores |= _enum(sub)
    return valores


def _campos(metodo: str, ruta: str, *camino: str) -> set:
    """Las propiedades de la respuesta 200, siguiendo `camino` por listas y objetos."""
    esquema = _resolver(_operacion(metodo, ruta)["responses"]["200"]["content"]["application/json"]["schema"])
    for paso in camino:
        esquema = _resolver(esquema["properties"][paso])
        if esquema.get("type") == "array":
            esquema = _resolver(esquema["items"])
    return set(esquema.get("properties", {}))


@pytest.mark.parametrize("metodo, ruta, enviados", ENDPOINTS, ids=lambda x: x if isinstance(x, str) else None)
def test_rutas_y_parametros_existen(metodo, ruta, enviados):
    assert ruta in OPENAPI["paths"] and metodo.lower() in OPENAPI["paths"][ruta], f"{metodo} {ruta}"
    operacion = _operacion(metodo, ruta)
    disponibles = {p["name"] for p in operacion.get("parameters", [])}
    if "requestBody" in operacion:
        disponibles |= set(_resolver(operacion["requestBody"]["content"]["application/json"]["schema"])["properties"])
    assert set(enviados) <= disponibles, f"{ruta}: {set(enviados) - disponibles}"


def test_enums_de_las_herramientas_dentro_de_los_del_core_api():
    alertas = POR_NOMBRE["listar_alertas"].Parametros.model_fields
    compras = POR_NOMBRE["recomendar_compras"].Parametros.model_fields
    assert set(TIPOS_IA) == _enum(_parametro("GET", "/api/alertas/ml", "tipo")["schema"])
    assert set(alertas["urgencia"].annotation.__args__[0].__args__) <= _enum(_parametro("GET", "/api/alertas/ml", "urgencia")["schema"])
    assert set(compras["urgencia"].annotation.__args__[0].__args__) == _enum(_parametro("GET", "/api/ml/recomendaciones/compras", "urgencia")["schema"])
    # /api/alertas y el semáforo del inventario no declaran enum (INV-64): se comparan con su descripción
    assert all(t in _parametro("GET", "/api/alertas", "tipo")["description"] for t in TIPOS_REGLAS)
    assert all(e in _parametro("GET", "/api/consulta/inventario", "semaforo")["description"]
               for e in ("ok", "bajo", "critico", "inconsistencia"))


@pytest.mark.parametrize("metodo, ruta, camino, leidos", [
    ("GET", "/api/auth/me", (), {"rol", "sucursal_nombre"}),
    ("GET", "/api/consulta/sucursales", ("items",), {"id_sucursal", "nombre", "tipo"}),
    ("GET", "/api/consulta/categorias", ("items",), {"categoria"}),
    ("GET", "/api/consulta/productos", ("items",), {"id_producto", "codigo_item", "nombre", "categoria", "unidad"}),
    ("GET", "/api/consulta/productos", (), {"items", "total"}),
    ("GET", "/api/consulta/inventario", ("items",), {"nombre_producto", "sucursal", "stock_disponible", "stock_minimo",
                                                     "dias_cobertura", "semaforo", "unidad"}),
    ("GET", "/api/consulta/inventario", (), {"items", "total", "fecha_inventario"}),
    ("GET", "/api/alertas", ("items",), {"nombre_producto", "sucursal", "tipo", "urgencia", "detalle"}),
    ("GET", "/api/alertas", (), {"items", "total", "fecha_inventario"}),
    ("GET", "/api/alertas/ml", ("items",), {"nombre_producto", "codigo_item", "sucursal", "tipo", "urgencia", "detalle"}),
    ("GET", "/api/alertas/ml", ("resumen",), {"critica", "alta", "media", *TIPOS_IA}),
    ("GET", "/api/alertas/resumen", ("items",), {"sucursal", "contadores"}),
    ("GET", "/api/alertas/resumen", ("global_",), {"critica", "alta", "media", "total"}),
    ("GET", "/api/alertas/resumen", (), {"por_tipo", "fecha_inventario"}),
    ("POST", "/api/ml/predict", (), {"prediccion_q50", "interpretacion", "fecha_features"}),
    ("GET", "/api/consulta/productos/{id_producto}/ventas", (), {"unidad", "fecha_fin", "ventanas"}),
    ("GET", "/api/consulta/productos/{id_producto}/ventas", ("ventanas",), {"desde", "hasta", "unidades"}),
    ("GET", "/api/ml/recomendaciones/compras", ("compras",), {"producto_id", "nombre_producto", "destino", "cantidad", "unidad",
                                                             "urgencia", "dias_hasta_agotarse", "fecha_pedido", "necesidad_sucursal"}),
    ("GET", "/api/ml/recomendaciones/compras", ("resumen",), {"lineas", "productos", "cantidad", "cubiertos_por_bodega"}),
    ("GET", "/api/ml/recomendaciones/compras", ("filtros_aplicados",), {"sucursal", "sucursal_por_rol"}),
    ("GET", "/api/ml/recomendaciones/compras", (), {"compras", "resumen", "fecha_inventario"}),
])
def test_campos_que_leen_las_herramientas(metodo, ruta, camino, leidos):
    faltan = leidos - _campos(metodo, ruta, *camino)
    assert not faltan, f"{ruta} {'.'.join(camino)}: {faltan}"
