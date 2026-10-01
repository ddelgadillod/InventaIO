"""INV-23 — Caché en memoria (C3) y traducción de los errores de ml_service (R5)."""
import threading
import time

import httpx
import pytest

from ml.cache import CacheRecomendaciones


# ── Caché a través de los endpoints ─────────────────

def test_la_segunda_llamada_y_otros_filtros_salen_de_la_cache(ctx):
    primera = ctx.get("compras").json()
    segunda = ctx.get("compras", sucursal="LA 21", urgencia="normal").json()
    assert ctx.ml.llamadas["/api/compras"] == 1
    assert ctx.ml.llamadas["/api/health"] == 2                 # la clave se arma en cada petición
    assert segunda["calculado_en"] == primera["calculado_en"]
    assert ctx.catalogo.lecturas_productos == 1                # el enriquecimiento también se guarda


def test_compras_y_transferencias_tienen_claves_distintas(ctx):
    ctx.get("compras")
    ctx.get("transferencias")
    ctx.get("transferencias", sucursal="GLORIETA")
    assert (ctx.ml.llamadas["/api/compras"], ctx.ml.llamadas["/api/transferencias"]) == (1, 1)
    assert sorted(c[0] for c in ctx.cache.claves()) == ["compras", "transferencias"]


@pytest.mark.parametrize("cambio", [
    lambda s: s.update(fecha_inventario="2026-01-15"),                       # foto nueva
    lambda s: s["politicas"]["inv21"].update(version=2),                     # políticas nuevas
    lambda s: s["politicas"]["inv22"].update(fecha="2026-10-15"),
])
def test_foto_o_politicas_nuevas_recalculan_y_descartan_la_clave_vieja(ctx, cambio):
    ctx.get("compras")
    cambio(ctx.ml.salud)
    ctx.get("compras")
    assert ctx.ml.llamadas["/api/compras"] == 2
    assert len(ctx.cache.claves()) == 1


# ── CacheRecomendaciones ────────────────────────────

def test_el_ttl_vencido_recalcula():
    ahora = [0.0]
    cache = CacheRecomendaciones(ttl_segundos=60, reloj=lambda: ahora[0])
    calculos = []
    calcular = lambda: calculos.append(1) or len(calculos)  # noqa: E731
    assert cache.obtener(("compras", "f"), calcular) == 1
    ahora[0] = 59
    assert cache.obtener(("compras", "f"), calcular) == 1
    ahora[0] = 61
    assert cache.obtener(("compras", "f"), calcular) == 2


def test_un_error_no_se_guarda():
    cache = CacheRecomendaciones(ttl_segundos=60)

    def falla():
        raise RuntimeError("ml_service caído")

    with pytest.raises(RuntimeError):
        cache.obtener(("compras", "f"), falla)
    assert cache.claves() == []
    assert cache.obtener(("compras", "f"), lambda: "ok") == "ok"


def test_peticiones_simultaneas_esperan_un_solo_calculo():
    cache = CacheRecomendaciones(ttl_segundos=60)
    calculos = []

    def lento():
        calculos.append(1)
        time.sleep(0.2)
        return "resultado"

    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(cache.obtener(("compras", "f"), lento)))
             for _ in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(calculos) == 1 and resultados == ["resultado"] * 5


# ── Errores de ml_service (R5) ──────────────────────

@pytest.mark.parametrize("ruta, falla, codigo, detalle", [
    ("/api/compras", (409, {"detail": "La foto de inventario es posterior: faltan las ventas de 2 día(s)"}), 409,
     "La foto de inventario es posterior: faltan las ventas de 2 día(s)"),
    ("/api/compras", (503, {"detail": "Bodega no disponible"}), 503, "ML Service: Bodega no disponible"),
    ("/api/compras", (500, {"detail": "Internal Server Error"}), 502, "ML Service respondió 500: Internal Server Error"),
    ("/api/compras", (422, {"detail": [{"msg": "campo inválido"}]}), 502, None),
    ("/api/compras", httpx.ConnectError("conexión rechazada"), 503, "ML Service no disponible"),
    ("/api/compras", httpx.ReadTimeout("lento"), 504, "ML Service no respondió en 5 s"),
    ("/api/health", httpx.ConnectError("conexión rechazada"), 503, "ML Service no disponible"),
])
def test_errores_de_ml_service_se_traducen_y_no_se_guardan(ctx, ruta, falla, codigo, detalle):
    ctx.ml.fallas[ruta] = falla
    r = ctx.get("compras")
    assert r.status_code == codigo, r.text
    if detalle is not None:
        assert r.json()["detail"] == detalle
    assert ctx.cache.claves() == []
    del ctx.ml.fallas[ruta]
    assert ctx.get("compras").status_code == 200                # se recupera sin reiniciar


@pytest.mark.parametrize("salud, codigo, detalle", [
    ({"status": "degradado", "bodega": "sin conexión", "fecha_inventario": None}, 503,
     "ML Service degradado: sin conexión a la bodega"),
    ({"fecha_inventario": None}, 503, "ML Service sin foto de inventario cargada"),
])
def test_health_degradado_o_sin_foto_da_503(ctx, salud, codigo, detalle):
    ctx.ml.salud.update(salud)
    r = ctx.get("transferencias")
    assert (r.status_code, r.json()["detail"]) == (codigo, detalle)
    assert ctx.ml.llamadas["/api/transferencias"] == 0


def test_ml_service_anterior_a_inv23_da_502(ctx):
    for campo in ("fecha_inventario", "politicas"):
        del ctx.ml.salud[campo]
    r = ctx.get("compras")
    assert r.status_code == 502 and "anterior a INV-23" in r.json()["detail"]


def test_error_sin_json_usa_el_texto():
    from fastapi import HTTPException

    from ml.cliente import ClienteML

    def html(request):
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    cliente = ClienteML("http://ml-service", timeout=5, transport=httpx.MockTransport(html))
    with pytest.raises(HTTPException) as exc:
        cliente.compras()
    assert exc.value.status_code == 502 and exc.value.detail == "ML Service respondió 502: <html>Bad Gateway</html>"
