"""
INV-23 — Fixtures de las pruebas del Core API.
Las pruebas unitarias no usan Postgres ni ml_service: el usuario, el catálogo
y ml_service se reemplazan con dobles (dependency_overrides y un transporte
falso de httpx). Las respuestas falsas tienen la forma real de
POST /api/compras y POST /api/transferencias (docs/ML-SERVICE-API.md).
La prueba contra los servicios reales está en test_recomendaciones_integracion.py.
"""
import collections
import json

import httpx
import pytest
from fastapi.testclient import TestClient

BODEGA = "BODEGA_CENTRAL"
SUCURSALES = {1: "PRINCIPAL", 2: "LA 21", 3: "GLORIETA", 5: BODEGA}   # sin SIN_SUCURSAL (4)
PRODUCTOS = {
    "P1": ("HUEVOS *UND", "Huevos"),
    "P2": ("AGUA CRISTAL LITRO SPORT", "Bebidas"),
    "P3": ("ARROZ ZULIA *500 GR", "Arroz"),
    "K1": ("TOMATE CHONTO *KL", "Frutas y verduras"),
    "L1": ("LECHE ENTERA *1100ML", "Lácteos"),
    "H1": ("VASO TUC 7 OZ *UND", "Hogar"),
    "S1": ("DET ARIEL LIQ *1800 ML", "Aseo hogar"),
    "A1": ("ANCHETA NAVIDEÑA", "Anchetas"),
}                                                                      # X9 no tiene fila (R6)
POLITICAS = {"inv21": {"version": 1, "fecha": "2026-09-30"}, "inv22": {"version": 1, "fecha": "2026-09-30"}}


# ── Respuestas falsas de ml_service ─────────────────

def _det(sucursal, necesidad, dias, urgencia, llega_tarde=False, motivo="reposicion"):
    return {"sucursal": sucursal, "posicion": 10.0, "q50": 20.0, "limite_superior": 30.0, "punto_pedido": 29.33,
            "nivel": 44.0, "necesidad": necesidad, "dias_hasta_agotarse": dias, "urgencia": urgencia,
            "llega_tarde": llega_tarde, "motivo": motivo}


def _linea(pid, destino, cantidad, necesidad, detalle, unidad="unidad", sobrante=None):
    bodega = destino == BODEGA
    peor = min(detalle, key=lambda d: d["dias_hasta_agotarse"])
    return {"producto_id": pid, "destino": destino, "tipo_destino": "bodega_central" if bodega else "sucursal",
            "grupo": "quincenal" if bodega else "semanal", "cantidad": cantidad, "unidad": unidad,
            "urgencia": peor["urgencia"], "dias_hasta_agotarse": peor["dias_hasta_agotarse"],
            "fecha_pedido": "2026-01-02" if bodega else "2026-01-06",
            "fecha_llegada": "2026-01-07" if bodega else "2026-01-11",
            "fecha_llegada_sucursal": "2026-01-09" if bodega else "2026-01-11",
            "llega_tarde": any(d["llega_tarde"] for d in detalle), "necesidad": necesidad,
            "sobrante_bodega": sobrante if bodega else None,
            "motivo": "stock_negativo" if any(d["motivo"] == "stock_negativo" for d in detalle) else "reposicion",
            "detalle": detalle}


def compras_ml() -> dict:
    return {
        "fecha_inventario": "2025-12-31", "fecha_pronostico": "2025-12-31", "lead_time_dias": 5,
        "politicas": POLITICAS,
        "calendario": [
            {"grupo": "quincenal", "tipo_destino": "bodega_central", "fecha_pedido": "2026-01-02",
             "fecha_llegada": "2026-01-07", "fecha_llegada_sucursal": "2026-01-09", "pedido_siguiente": "2026-01-16",
             "cubre_hasta": "2026-01-23", "dias_cubiertos": 22, "dias_hasta_llegada": 8},
            {"grupo": "semanal", "tipo_destino": "sucursal", "fecha_pedido": "2026-01-06",
             "fecha_llegada": "2026-01-11", "fecha_llegada_sucursal": "2026-01-11", "pedido_siguiente": "2026-01-13",
             "cubre_hasta": "2026-01-18", "dias_cubiertos": 17, "dias_hasta_llegada": 10},
        ],
        "compras": [
            _linea("P1", "PRINCIPAL", 50, 49.3, [_det("PRINCIPAL", 49.3, 2.2, "urgente", llega_tarde=True)]),
            # La Bodega compra por PRINCIPAL (normal) y LA 21 (stock negativo): la línea es urgente
            _linea("P2", BODEGA, 47, 46.86, [_det("PRINCIPAL", 36.95, 10.5, "normal"),
                                             _det("LA 21", 9.91, 0.0, "urgente", True, "stock_negativo")], sobrante=0.0),
            _linea("P3", BODEGA, 20, 25.5, [_det("GLORIETA", 25.5, 7.0, "alta")], sobrante=6.0),
            _linea("K1", "LA 21", 8, 7.2, [_det("LA 21", 7.2, 12.0, "normal")], unidad="kg"),
            _linea("X9", "GLORIETA", 3, 2.5, [_det("GLORIETA", 2.5, 13.0, "normal")]),
        ],
        "cubrir_con_traslado": [
            {"producto_id": "L1", "necesidad": 30.0, "sobrante_bodega": 40.0, "unidad": "unidad",
             "urgencia": "alta", "dias_hasta_agotarse": 8.0,
             "detalle": [_det("PRINCIPAL", 12.0, 14.0, "normal"), _det("GLORIETA", 18.0, 8.0, "alta")]},
        ],
        "alertas": [
            {"producto_id": "P2", "sucursal": "LA 21", "tipo": "posible_inconsistencia_inventario", "stock": -1.0,
             "accion": "compra_urgente", "detalle": "Stock negativo en la foto: verificar el conteo."},
            {"producto_id": "H1", "sucursal": BODEGA, "tipo": "posible_inconsistencia_inventario", "stock": -5.0,
             "accion": "verificar_conteo", "detalle": "Stock negativo en la foto: verificar el conteo."},
        ],
        "no_encontrados": [],
        "resumen": {"productos": 9, "lineas": 5, "lineas_sucursal": 3, "lineas_bodega": 2,
                    "cantidad": {"unidad": 120, "kg": 8}, "cubiertos_por_bodega": 1, "alertas": 2,
                    "pares_sin_pronostico": 4},
    }


def _bal(pid, sucursal, estado, urgencia, deficit, deficit_neto, recibido=0, excedente_sin_destino=0.0,
         unidad="unidad"):
    bodega = sucursal == BODEGA
    return {"producto_id": pid, "sucursal": sucursal, "tipo_ubicacion": "bodega_central" if bodega else "sucursal",
            "rama": None if bodega or estado == "sin_pronostico" else "intermitente", "stock": 8.0,
            "q50": None if bodega else 20.0, "limite_superior": None if bodega else 30.0, "objetivo": None,
            "maximo": None, "excedente": None, "excedente_sin_destino": excedente_sin_destino, "deficit": deficit,
            "deficit_vigilancia": None, "recibido": recibido, "enviado": 0, "deficit_neto": deficit_neto,
            "estado": estado, "urgencia": urgencia, "dias_hasta_agotarse": None, "unidad": unidad}


def _traslado(pid, origen, destino, cantidad, urgencia, unidad="unidad"):
    return {"producto_id": pid, "origen": origen, "destino": destino, "cantidad": cantidad, "unidad": unidad,
            "urgencia": urgencia, "dias_hasta_agotarse": 1.5, "fecha_llegada": "2026-01-03",
            "dias_habiles_llegada": 2, "llega_tarde": False}


def transferencias_ml() -> dict:
    return {
        "fecha_inventario": "2025-12-31", "fecha_pronostico": "2025-12-31", "horizonte_dias": 15,
        "politicas": POLITICAS["inv22"],
        "traslados": [
            _traslado("P1", BODEGA, "PRINCIPAL", 10, "urgente"),
            _traslado("P2", "GLORIETA", "LA 21", 6, "alta"),
            _traslado("P3", "LA 21", "PRINCIPAL", 4, "normal"),
            _traslado("K1", BODEGA, "LA 21", 3, "urgente", unidad="kg"),
        ],
        "balance": [
            _bal("P1", "PRINCIPAL", "destino", "urgente", 20.0, 10.0, recibido=10),
            _bal("P1", BODEGA, "bodega", None, None, None, excedente_sin_destino=5.0),
            _bal("P2", "LA 21", "destino", "alta", 8.0, 2.0, recibido=6),
            _bal("P3", "PRINCIPAL", "equilibrio", "normal", 0.0, 0.0, recibido=4),
            _bal("K1", "LA 21", "destino", "urgente", 4.5, 1.5, recibido=3, unidad="kg"),
            _bal("L1", "GLORIETA", "vigilancia", "vigilancia", 0.0, 0.0),
            _bal("S1", "GLORIETA", "sin_pronostico", None, None, None),
        ],
        "alertas": [
            {"producto_id": "P2", "sucursal": "PRINCIPAL", "tipo": "stock_negativo", "stock": -2.0,
             "accion": "pedido_urgente", "detalle": "Stock negativo en la foto: verificar el conteo."},
            {"producto_id": "S1", "sucursal": "GLORIETA", "tipo": "sin_pronostico", "stock": 1.0,
             "accion": "ninguna", "detalle": "Sin pronóstico: no participa en los traslados."},
        ],
        "no_encontrados": [],
        "resumen": {"productos": 6, "traslados": 4, "cantidad_trasladada": 23, "deficit_total": 32.5,
                    "deficit_neto": 13.5, "excedente_sin_destino": 5.0, "alertas": 2},
    }


def salud_ml(**cambios) -> dict:
    salud = {"status": "ok", "service": "inventaio-ml-service",
             "modelos_cargados": ["intermitente", "suave_no_perecedero", "suave_perecedero"], "bodega": "ok",
             "fecha_inventario": "2025-12-31", "politicas": json.loads(json.dumps(POLITICAS))}
    salud.update(cambios)
    return salud


class MLFalso:
    """Responde como ml_service. `fallas` fuerza una respuesta (código, cuerpo)
    o una excepción de httpx por ruta. Cuenta las llamadas y guarda los cuerpos."""

    def __init__(self):
        self.salud = salud_ml()
        self.respuestas = {"/api/compras": compras_ml(), "/api/transferencias": transferencias_ml()}
        self.fallas: dict = {}
        self.llamadas = collections.Counter()
        self.cuerpos: dict = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        self.llamadas[ruta] += 1
        if request.content:
            self.cuerpos[ruta] = json.loads(request.content)
        falla = self.fallas.get(ruta)
        if isinstance(falla, Exception):
            raise falla
        if falla is not None:
            return httpx.Response(falla[0], json=falla[1])
        if ruta == "/api/health":
            return httpx.Response(200, json=self.salud)
        return httpx.Response(200, json=self.respuestas[ruta])


class CatalogoFijo:
    def __init__(self):
        self.lecturas_productos = 0

    def sucursales(self) -> dict:
        return dict(SUCURSALES)

    def categorias(self) -> list:
        return sorted({c for _, c in PRODUCTOS.values()})

    def productos(self) -> dict:
        self.lecturas_productos += 1
        return dict(PRODUCTOS)


def usuario(rol: str, id_sucursal=None):
    from models.usuario import Usuario

    return Usuario(id=1, email=f"{rol}@inventaio.co", nombre=rol, rol=rol, id_sucursal=id_sucursal, activo=True)


class Contexto:
    """TestClient con los dobles a mano: `como` cambia el usuario autenticado."""

    def __init__(self, http, ml, cache, catalogo, estado):
        self.http, self.ml, self.cache, self.catalogo, self._estado = http, ml, cache, catalogo, estado

    def como(self, rol: str, id_sucursal=None) -> "Contexto":
        self._estado["usuario"] = usuario(rol, id_sucursal)
        return self

    def get(self, ruta: str, **params) -> httpx.Response:
        return self.http.get(f"/api/ml/recomendaciones/{ruta}", params=params)


@pytest.fixture()
def ml():
    return MLFalso()


@pytest.fixture()
def ctx(ml):
    from auth.dependencies import get_current_user
    from main import app
    from ml.cache import CacheRecomendaciones, get_cache
    from ml.catalogo import get_catalogo
    from ml.cliente import ClienteML, get_cliente_ml

    estado = {"usuario": usuario("gerente")}
    cache = CacheRecomendaciones(ttl_segundos=3600)
    catalogo = CatalogoFijo()
    cliente_ml = ClienteML("http://ml-service", timeout=5, transport=httpx.MockTransport(ml))
    app.dependency_overrides.update({
        get_current_user: lambda: estado["usuario"],
        get_catalogo: lambda: catalogo,
        get_cliente_ml: lambda: cliente_ml,
        get_cache: lambda: cache,
    })
    with TestClient(app) as http:
        yield Contexto(http, ml, cache, catalogo, estado)
    app.dependency_overrides.clear()
