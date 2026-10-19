"""Cliente del Core API (INV-32, T10): token del usuario, request_id y errores para el modelo (C11)."""
import httpx
import pytest

from core.config import Settings
from herramientas.core_api import ClienteCoreAPI, ErrorHerramienta
from tests.conftest import TOKEN


async def test_reenvia_el_token_y_el_request_id(ctx, core_api):
    await ctx.get("/api/consulta/inventario", sucursal_id=3, semaforo=None, page_size=10)
    r = core_api.peticiones[-1]
    assert r.headers["authorization"] == TOKEN["Authorization"] and r.headers["x-request-id"] == "req-1"
    assert core_api.params() == {"sucursal_id": "3", "page_size": "10"}      # sin los filtros vacíos
    assert str(r.url).startswith("http://core-falso:8000/api/")


@pytest.mark.parametrize("status, cuerpo, mensaje", [
    (403, {"detail": "Solo puede consultar su sucursal (PRINCIPAL)"}, "Solo puede consultar su sucursal (PRINCIPAL)"),
    (422, {"detail": [{"type": "value_error", "msg": "Value error, indicar sucursal_id (nombre) o id_sucursal"},
                      {"msg": "otro"}]}, "Value error, indicar sucursal_id (nombre) o id_sucursal; otro"),
    (500, None, "Internal Server Error"),
])
async def test_errores_con_el_mensaje_del_core_api(status, cuerpo, mensaje):
    def responder(request):
        return httpx.Response(status, json=cuerpo) if cuerpo else httpx.Response(status, text="Internal Server Error")
    core = ClienteCoreAPI(Settings(CORE_API_URL="http://x"), transport=httpx.MockTransport(responder))
    with pytest.raises(ErrorHerramienta) as e:
        await core.pedir("GET", "/api/alertas", "Bearer t", "r")
    assert (e.value.status, e.value.mensaje) == (status, mensaje)
    assert e.value.para_modelo() == {"error": {"status": status, "mensaje": mensaje}}


async def test_tiempo_agotado_y_caida(ctx, core_api):
    core_api.lento = True
    with pytest.raises(ErrorHerramienta) as e:
        await ctx.get("/api/alertas/ml")
    assert e.value.status == 504 and "60 s" in e.value.mensaje
    core_api.lento, core_api.caido = False, True
    with pytest.raises(ErrorHerramienta) as e:
        await ctx.get("/api/alertas")
    assert (e.value.status, e.value.mensaje) == (503, "El Core API no está disponible")
