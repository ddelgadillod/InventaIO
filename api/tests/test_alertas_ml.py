"""INV-28 — GET /api/alertas/ml: reglas V2 a V6, V10 y V11, permisos, filtros,
paginación, caché compartida con Recomendaciones y errores del ML Service.
Sin Postgres ni ml_service: dobles del conftest con un balance a la medida.
Ver docs/INV-28-requerimientos.md."""
import httpx
import pytest

from tests.conftest import BODEGA, POLITICAS

# ids de CatalogoFijo.ids_producto(): P1 101, P2 102, P3 103, K1 104, L1 105, H1 106, S1 107, A1 108


def _fila(pid, sucursal, stock, q50, maximo=None, urgencia="normal", dias=None, unidad="unidad", estado="destino"):
    bodega = sucursal == BODEGA
    return {"producto_id": pid, "sucursal": sucursal, "tipo_ubicacion": "bodega_central" if bodega else "sucursal",
            "rama": None if q50 is None else "intermitente", "stock": stock, "q50": q50,
            "limite_superior": None if q50 is None else q50 * 1.4, "objetivo": q50, "maximo": maximo,
            "excedente": None, "excedente_sin_destino": None, "deficit": None, "deficit_vigilancia": None,
            "recibido": 0, "enviado": 0, "deficit_neto": None, "estado": estado, "urgencia": urgencia,
            "dias_hasta_agotarse": dias, "unidad": unidad}


def transferencias_alertas() -> dict:
    return {
        "fecha_inventario": "2025-12-31", "fecha_pronostico": "2025-12-31", "horizonte_dias": 15,
        "politicas": POLITICAS["inv22"],
        "traslados": [
            {"producto_id": "P1", "origen": BODEGA, "destino": "PRINCIPAL", "cantidad": 10, "unidad": "unidad",
             "urgencia": "urgente", "dias_hasta_agotarse": 2.18, "fecha_llegada": "2026-01-05",
             "dias_habiles_llegada": 2, "llega_tarde": False},
        ],
        "balance": [
            _fila("P1", "PRINCIPAL", 489, 3366.01, 6913.0, "urgente", 2.18),          # riesgo, ambos, con traslado
            _fila("P2", "PRINCIPAL", 0, 1.86, 3.0, "urgente", 0.0),                   # riesgo con stock 0, ml
            _fila("P3", "LA 21", 0, 0.66, 1.0, "urgente", 0.0),                       # q50 < 1: sin alerta
            _fila("H1", "LA 21", -1, 5.0, 8.0, "urgente", 0.0, estado="stock_negativo"),  # ya es inconsistencia
            _fila("L1", "GLORIETA", 30, 40.0, 60.0, "alta", 7.5),                     # riesgo alta
            _fila("P2", "GLORIETA", 15, 20.0, 30.0, "normal", 11.25),                 # normal: sin alerta
            _fila("S1", "GLORIETA", 404, 12.3, 18.36, estado="origen"),               # sobrestock 22 veces
            _fila("A1", "GLORIETA", 37, 10.0, 18.5, estado="origen"),                 # justo 2 × máximo: no
            _fila("K1", "LA 21", 77.1, 30.0, 20.0, unidad="kg", estado="origen"),     # sobrestock en kg
            _fila("P3", "PRINCIPAL", 50, 0.0, None, "vigilancia", estado="vigilancia"),  # q50 = 0: sin_movimiento
            _fila("P1", BODEGA, 4024, None, estado="bodega"),                         # la Bodega no genera
            _fila("S1", "PRINCIPAL", 3, None, estado="sin_pronostico"),
        ],
        "alertas": [],
        "no_encontrados": [],
        "resumen": {},
    }


@pytest.fixture()
def alertas(ctx):
    ctx.ml.respuestas["/api/transferencias"] = transferencias_alertas()
    ctx.reglas.pares = {(1, 101)}                                 # HUEVOS en PRINCIPAL: stock_critico en reglas

    def get(**params):
        return ctx.http.get("/api/alertas/ml", params=params)
    ctx.alertas = get
    return ctx


def _claves(body):
    return [(a["codigo_item"], a["sucursal"], a["tipo"]) for a in body["items"]]


def test_reglas_v3_v4_y_orden(alertas):
    body = alertas.alertas().json()
    assert _claves(body) == [
        ("P2", "PRINCIPAL", "riesgo_desabastecimiento_ml"),       # crítica, 0 días
        ("P1", "PRINCIPAL", "riesgo_desabastecimiento_ml"),       # crítica, 2,18 días
        ("L1", "GLORIETA", "riesgo_desabastecimiento_ml"),        # alta
        ("S1", "GLORIETA", "sobrestock_previsto_ml"),             # media, 22 veces el máximo
        ("K1", "LA 21", "sobrestock_previsto_ml"),                # media, 3,86 veces
    ]
    assert body["total"] == 5
    assert body["resumen"] == {"total": 5, "riesgo_desabastecimiento_ml": 3, "sobrestock_previsto_ml": 2,
                               "critica": 2, "alta": 1, "media": 2, "ambos": 1, "ml": 4}
    assert body["fecha_inventario"] == "2025-12-31" and body["politicas"] == POLITICAS["inv22"]
    assert "calculado_en" in body and "page" not in body


def test_urgencias_umbrales_y_origen(alertas):
    por_clave = {(a["codigo_item"], a["sucursal"]): a for a in alertas.alertas().json()["items"]}
    huevos = por_clave[("P1", "PRINCIPAL")]
    assert (huevos["urgencia"], huevos["umbral"], huevos["valor"], huevos["origen"]) == ("critica", 5.0, 2.18, "ambos")
    assert (huevos["id_producto"], huevos["id_sucursal"], huevos["nombre_producto"]) == (101, 1, "HUEVOS *UND")
    assert por_clave[("P2", "PRINCIPAL")]["origen"] == "ml"
    leche = por_clave[("L1", "GLORIETA")]
    assert (leche["urgencia"], leche["umbral"]) == ("alta", 10.0)
    sobre = por_clave[("S1", "GLORIETA")]
    assert (sobre["urgencia"], sobre["umbral"], sobre["valor"], sobre["origen"]) == ("media", 2.0, 22.0, "ml")


def test_detalles_con_traslado_sugerido_y_kilos(alertas):
    por_clave = {(a["codigo_item"], a["sucursal"]): a["detalle"] for a in alertas.alertas().json()["items"]}
    assert por_clave[("P1", "PRINCIPAL")] == (
        "Stock 489 unidades; con la demanda prevista (3.366 unidades en 15 días hábiles) alcanza 2,2 días "
        "hábiles; traslado sugerido: 10 unidades desde BODEGA_CENTRAL")
    assert por_clave[("P2", "PRINCIPAL")].endswith("alcanza 0,0 días hábiles")      # sin traslado
    assert por_clave[("K1", "LA 21")] == (
        "Stock 77,1 kg: 3,9 veces el máximo (20,0 kg); demanda prevista 30,0 kg en 15 días hábiles")


def test_filtros_tipo_urgencia_y_origen(alertas):
    assert alertas.alertas(tipo="sobrestock_previsto_ml").json()["total"] == 2
    assert alertas.alertas(urgencia="critica").json()["total"] == 2
    body = alertas.alertas(origen="ambos").json()
    assert _claves(body) == [("P1", "PRINCIPAL", "riesgo_desabastecimiento_ml")]
    assert body["resumen"]["total"] == 1                         # el resumen cuenta lo filtrado


@pytest.mark.parametrize("params", [{"tipo": "stock_bajo"}, {"urgencia": "urgente"}, {"origen": "reglas"},
                                    {"page": 0}, {"page_size": 501}])
def test_parametros_invalidos_422(alertas, params):
    assert alertas.alertas(**params).status_code == 422


def test_paginacion(alertas):
    body = alertas.alertas(page=2, page_size=2).json()
    assert (body["page"], body["page_size"], body["pages"], body["total"]) == (2, 2, 3, 5)
    assert _claves(body) == [("L1", "GLORIETA", "riesgo_desabastecimiento_ml"),
                             ("S1", "GLORIETA", "sobrestock_previsto_ml")]
    assert alertas.alertas(page=1).json()["page_size"] == 50


def test_admin_sucursal_ve_solo_la_suya(alertas):
    alertas.como("admin_sucursal", id_sucursal=2)
    body = alertas.alertas().json()
    assert _claves(body) == [("K1", "LA 21", "sobrestock_previsto_ml")]
    assert alertas.alertas(sucursal_id=2).json()["total"] == 1


@pytest.mark.parametrize("sucursal_id, detalle", [
    (1, "Solo puede consultar su sucursal (LA 21)"),
    (5, "Solo puede consultar su sucursal (LA 21); la Bodega Central, solo en el stock"),
])
def test_admin_sucursal_otra_ubicacion_403_sin_llamar_al_ml(alertas, sucursal_id, detalle):
    r = alertas.como("admin_sucursal", id_sucursal=2).alertas(sucursal_id=sucursal_id)
    assert r.status_code == 403 and r.json()["detail"] == detalle
    assert alertas.ml.llamadas["/api/transferencias"] == 0


@pytest.mark.parametrize("sucursal_id", [4, 99])               # SIN_SUCURSAL o inexistente
def test_sucursal_invalida_422(alertas, sucursal_id):
    assert alertas.alertas(sucursal_id=sucursal_id).status_code == 422


def test_gerente_filtra_una_sucursal_y_la_bodega_no_tiene_alertas(alertas):
    assert alertas.alertas(sucursal_id=3).json()["total"] == 2                 # GLORIETA: L1 y S1
    body = alertas.como("admin_bodega", id_sucursal=5).alertas(sucursal_id=5).json()
    assert body["total"] == 0 and body["items"] == []


def test_sin_token_403(alertas):
    from auth.dependencies import get_current_user
    from main import app

    del app.dependency_overrides[get_current_user]
    assert alertas.http.get("/api/alertas/ml").status_code == 403


def test_comparte_la_cache_con_recomendaciones(alertas):
    assert alertas.get("transferencias").status_code == 200
    assert alertas.alertas().status_code == 200
    assert alertas.alertas(tipo="riesgo_desabastecimiento_ml").status_code == 200
    assert alertas.ml.llamadas["/api/transferencias"] == 1
    assert alertas.ml.cuerpos["/api/transferencias"] == {"incluir_balance": True}


@pytest.mark.parametrize("falla, codigo", [
    (httpx.ConnectError("sin conexión"), 503),
    (httpx.ReadTimeout("lento"), 504),
    ((409, {"detail": "La foto de inventario es posterior a la última venta"}), 409),
])
def test_errores_del_ml_service_se_traducen(alertas, falla, codigo):
    alertas.ml.fallas["/api/transferencias"] = falla
    assert alertas.alertas().status_code == codigo


def test_no_modifica_lo_guardado_en_la_cache(alertas):
    alertas.alertas()
    guardado = next(v for k, v in alertas.cache._datos.items() if k[0] == "transferencias")[1]
    fila = guardado["respuesta"]["balance"][0]
    assert set(fila) >= {"producto_id", "nombre_producto"} and "tipo" not in fila


# ── V13: varios valores por filtro ───────────────────
def test_varios_valores_por_filtro(alertas):
    assert alertas.alertas(urgencia=["critica", "alta"]).json()["total"] == 3
    body = alertas.alertas(tipo=["riesgo_desabastecimiento_ml", "sobrestock_previsto_ml"], origen=["ml"]).json()
    assert body["total"] == 4 and body["resumen"]["ambos"] == 0
    assert alertas.alertas(urgencia=["media"], origen=["ml", "ambos"]).json()["total"] == 2


def test_un_valor_invalido_entre_varios_422(alertas):
    assert alertas.alertas(urgencia=["critica", "urgente"]).status_code == 422
