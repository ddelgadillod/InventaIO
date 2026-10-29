"""INV-23 — Autenticación y permisos por rol (C1) en los dos endpoints."""
import pytest

RUTAS = ["compras", "transferencias"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_sin_token_403_y_token_invalido_401(ctx, ruta):
    from auth.dependencies import get_current_user
    from main import app

    del app.dependency_overrides[get_current_user]          # la dependencia real
    r = ctx.http.get(f"/api/ml/recomendaciones/{ruta}")
    assert r.status_code == 403                               # 401 desde FastAPI 0.12x: ver BearerSinToken403
    assert r.json()["detail"] == "Not authenticated"
    r = ctx.http.get(f"/api/ml/recomendaciones/{ruta}", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert r.status_code == 401
    assert ctx.ml.llamadas["/api/health"] == 0


@pytest.mark.parametrize("ruta", RUTAS)
def test_admin_sucursal_sin_parametro_ve_su_sucursal(ctx, ruta):
    body = ctx.como("admin_sucursal", id_sucursal=2).get(ruta).json()
    assert body["filtros_aplicados"]["sucursal"] == "LA 21"
    assert body["filtros_aplicados"]["sucursal_por_rol"] is True


@pytest.mark.parametrize("ruta", RUTAS)
def test_admin_sucursal_con_la_suya_200_y_con_otra_403(ctx, ruta):
    ctx.como("admin_sucursal", id_sucursal=1)
    r = ctx.get(ruta, sucursal="principal")
    assert r.status_code == 200 and r.json()["filtros_aplicados"]["sucursal_por_rol"] is False
    r = ctx.get(ruta, sucursal="GLORIETA")
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo puede consultar su sucursal (PRINCIPAL)"


@pytest.mark.parametrize("id_sucursal", [None, 4])          # sin sucursal, o SIN_SUCURSAL
def test_admin_sucursal_sin_sucursal_valida_403(ctx, id_sucursal):
    r = ctx.como("admin_sucursal", id_sucursal=id_sucursal).get("compras")
    assert r.status_code == 403
    assert r.json()["detail"] == "El usuario no tiene una sucursal asignada"


@pytest.mark.parametrize("rol, id_sucursal", [("gerente", None), ("admin_bodega", 5)])
def test_gerente_y_admin_bodega_ven_todo_y_filtran_cualquier_sucursal(ctx, rol, id_sucursal):
    ctx.como(rol, id_sucursal)
    body = ctx.get("compras").json()
    assert body["filtros_aplicados"]["sucursal"] is None and len(body["compras"]) == 5
    assert ctx.get("compras", sucursal="GLORIETA").status_code == 200
    assert ctx.get("transferencias", sucursal="LA 21").status_code == 200


def test_la_sucursal_desconocida_se_valida_antes_que_el_permiso(ctx):
    assert ctx.como("admin_sucursal", id_sucursal=1).get("compras", sucursal="Norte").status_code == 422
