"""Las 8 herramientas del catálogo v1 (INV-32) contra el Core API simulado con las formas reales."""
import pytest

from herramientas.base import MAX_FILAS, OMITIR, ErrorArgumentos, esquema_parametros
from herramientas.catalogo import CATALOGO, POR_NOMBRE, esquemas
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta


async def correr(ctx, nombre, **argumentos):
    h = POR_NOMBRE[nombre]
    return await h.ejecutar(ctx, h.validar(argumentos))


def test_catalogo_de_8_en_formato_ollama():
    nombres = [h["function"]["name"] for h in esquemas()]
    assert nombres == ["buscar_producto", "listar_sucursales", "consultar_inventario", "listar_alertas",
                       "resumen_alertas", "pronosticar_demanda", "historial_ventas", "recomendar_compras"]
    assert "detalle_inventario" not in nombres                                  # T1
    inventario = POR_NOMBRE["consultar_inventario"].esquema()["function"]["parameters"]
    assert inventario["required"] == [] and inventario["properties"]["estado"]["enum"] == ["ok", "bajo", "critico", "inconsistencia"]
    assert all(OMITIR in p["description"] for p in inventario["properties"].values())
    assert esquema_parametros(POR_NOMBRE["pronosticar_demanda"].Parametros)["required"] == ["producto"]   # T9


@pytest.mark.parametrize("argumentos, esperado", [
    ({"sucursal": "glorieta", "estado": "crítico"}, {"sucursal": "GLORIETA", "estado": "critico"}),
    ({"sucursal": "La21", "producto": "null", "categoria": "todas"}, {"sucursal": "LA 21"}),
    ({"estado": '["bajo"]', "producto": ["arroz"]}, {"estado": "bajo", "producto": "arroz"}),
    ({"sucursal": None, "inventado": 3}, {}),
])
def test_argumentos_tolerantes(argumentos, esperado):
    p = POR_NOMBRE["consultar_inventario"].validar(argumentos)
    assert p.model_dump(exclude_none=True) == esperado


@pytest.mark.parametrize("nombre, argumentos, texto", [
    ("consultar_inventario", {"estado": "rojo"}, "«estado» no admite 'rojo'"),
    ("pronosticar_demanda", {"sucursal": "GLORIETA"}, "falta «producto»"),
    ("pronosticar_demanda", {"producto": "huevos", "sucursal": "BODEGA_CENTRAL"}, "«sucursal» no admite"),
])
def test_argumentos_invalidos_con_lo_que_hay_que_corregir(nombre, argumentos, texto):
    with pytest.raises(ErrorArgumentos) as e:
        POR_NOMBRE[nombre].validar(argumentos)
    assert texto in str(e.value) and "Corrígelos" in str(e.value)


async def test_buscar_producto(ctx):
    r = await correr(ctx, "buscar_producto", texto="arroz carolina")
    assert r.para_modelo["total"] == 4 and r.data is None and r.fecha_dato is None
    assert r.para_modelo["filas"][0] == {"codigo": "P618", "nombre": "ARROZ CAROLINA *500 GR", "categoria": "Arroz", "unidad": "unidad"}


async def test_listar_sucursales(ctx):
    r = await correr(ctx, "listar_sucursales")
    assert r.para_modelo["filas"][3] == {"nombre": "BODEGA_CENTRAL", "tipo": "bodega central (solo abastece a las sucursales)"}
    assert r.data is None


async def test_consultar_inventario_filtros_y_data(ctx, core_api):
    r = await correr(ctx, "consultar_inventario", sucursal="GLORIETA", estado="critico", categoria="velas y velones")
    assert core_api.params() == {"sucursal_id": "3", "categoria": "Velas y velones", "semaforo": "critico",
                                 "page": "1", "page_size": str(MAX_FILAS)}
    assert r.para_modelo["filas"] == [{"producto": "VELON N. 2 VELAS LUZ DE ORO", "sucursal": "GLORIETA", "stock": "0 unidades",
                                       "minimo": "1 unidad", "cobertura": "0,0 d", "semaforo": "critico"}]
    assert r.fecha_dato == "2025-12-31" and r.para_modelo["total"] == 1
    assert r.data["forma"] == "tabla" and r.data["titulo"] == "Inventario · GLORIETA · crítico"
    assert [c["tipo"] for c in r.data["columnas"]] == ["texto", "texto", "cantidad", "cantidad", "texto", "semaforo"]
    assert r.data["filas"] == r.para_modelo["filas"] and (r.data["total"], r.data["mostrando"]) == (1, 1)   # T5


async def test_inventario_por_kilo_y_varias_palabras(ctx):
    r = await correr(ctx, "consultar_inventario", producto="papa pastusa")
    assert r.para_modelo["filas"][0]["stock"] == "77,1 kg"
    r = await correr(ctx, "consultar_inventario", producto="arroz carolina 500")      # C4
    assert r.para_modelo["total"] == 1 and r.para_modelo["filas"][0]["producto"] == "ARROZ CAROLINA *500 GR"


async def test_inventario_sin_resultados_no_genera_data(ctx):
    r = await correr(ctx, "consultar_inventario", producto="zzzz")
    assert r.para_modelo["total"] == 0 and r.data is None


async def test_alertas_de_reglas_por_defecto(ctx, core_api):
    h = POR_NOMBRE["listar_alertas"]
    p = h.validar({"sucursal": "GLORIETA", "urgencia": "critica"})
    assert not h.lenta(p) and h.etiqueta(p) == "Alertas · GLORIETA · crítica"
    r = await h.ejecutar(ctx, p)
    assert core_api.rutas()[-1] == "/api/alertas" and core_api.params()["page_size"] == str(MAX_FILAS)   # C8
    assert r.para_modelo["origen"] == "reglas" and r.para_modelo["total"] == 2
    assert [c["tipo"] for c in r.data["columnas"]][-2:] == ["urgencia", "texto"]


@pytest.mark.parametrize("argumentos", [{"origen": "ia"}, {"tipo": "riesgo_desabastecimiento_ml"}])
async def test_alertas_con_ia(ctx, core_api, argumentos):
    h = POR_NOMBRE["listar_alertas"]
    p = h.validar(argumentos)
    assert h.lenta(p) and h.etiqueta(p) == "Alertas con IA"                  # T7
    r = await h.ejecutar(ctx, p)
    assert core_api.rutas()[-1] == "/api/alertas/ml"
    assert r.para_modelo["por_urgencia"] == {"critica": 483, "alta": 383, "media": 721}


async def test_alertas_tipo_y_origen_que_no_coinciden(ctx):
    with pytest.raises(ErrorHerramienta) as e:
        await correr(ctx, "listar_alertas", origen="reglas", tipo="sobrestock_previsto_ml")
    assert e.value.status == 422 and "origen 'ia'" in e.value.mensaje


async def test_alertas_403_para_otra_sucursal(core):
    ctx = Contexto(core, "Bearer token-la21", "r")
    with pytest.raises(ErrorHerramienta) as e:
        await correr(ctx, "listar_alertas", sucursal="GLORIETA")
    assert (e.value.status, e.value.mensaje) == (403, "Solo puede consultar su sucursal (LA 21)")


async def test_resumen_de_alertas(ctx):
    r = await correr(ctx, "resumen_alertas")
    assert r.para_modelo["global"] == {"critica": "1.334", "alta": "386", "media": "2.732", "total": "4.452"}
    assert r.para_modelo["por_tipo"]["sin_movimiento"] == "2.453" and len(r.data["filas"]) == 4


async def test_pronostico_de_una_sucursal_es_tarjeta(ctx, core_api):
    r = await correr(ctx, "pronosticar_demanda", producto="huevos *und", sucursal="GLORIETA")
    assert core_api.peticiones[-1].url.path == "/api/ml/predict"
    assert r.para_modelo["demanda"] == "3.871 unidades" and "limite_superior" not in str(r.para_modelo)   # C9
    assert r.data["forma"] == "tarjeta" and r.data["titulo"] == "Pronóstico · HUEVOS *UND · GLORIETA"


@pytest.mark.parametrize("token, sucursales", [
    ("Bearer token-de-prueba", ["PRINCIPAL", "LA 21", "GLORIETA"]),
    ("Bearer token-bodega", ["PRINCIPAL", "LA 21", "GLORIETA"]),
    ("Bearer token-la21", ["LA 21"]),
])
async def test_pronostico_sin_sucursal_segun_el_rol(core, token, sucursales):            # T9
    r = await correr(Contexto(core, token, "r"), "pronosticar_demanda", producto="P1632")
    if len(sucursales) == 1:                     # la tarjeta lleva la sucursal en el título
        assert r.data["forma"] == "tarjeta" and r.data["titulo"].endswith(sucursales[0])
    else:
        assert r.data["forma"] == "tabla" and [f["sucursal"] for f in r.data["filas"]] == sucursales


async def test_pronostico_producto_ambiguo_no_llama_al_modelo(ctx, core_api):
    r = await correr(ctx, "pronosticar_demanda", producto="arroz carolina")
    assert r.para_modelo["resultado"] == "ambiguo" and r.data is None
    assert "/api/ml/predict" not in core_api.rutas()


async def test_pronostico_con_una_sucursal_que_falla(ctx, core_api):
    core_api.forzar["/api/ml/predict"] = (503, "El modelo no está disponible")
    with pytest.raises(ErrorHerramienta) as e:
        await correr(ctx, "pronosticar_demanda", producto="P1632")
    assert e.value.status == 503


async def test_ventas_de_una_y_de_tres_sucursales(ctx, core_api):
    r = await correr(ctx, "historial_ventas", producto="P1632", sucursal="GLORIETA")
    assert core_api.params() == {"sucursal_id": "3", "ventanas": "8"} and len(r.data["filas"]) == 8
    assert r.para_modelo["filas"][-1] == {"sucursal": "GLORIETA", "desde": "2025-12-17", "hasta": "2025-12-31", "ventas": "4.497 unidades"}
    assert [c["clave"] for c in r.data["columnas"]] == ["desde", "hasta", "ventas"]
    r = await correr(ctx, "historial_ventas", producto="P1632")                         # T4
    assert len(r.data["filas"]) == 9 and r.data["columnas"][0]["clave"] == "sucursal"
    assert set(r.para_modelo["suma_por_sucursal"]) == {"PRINCIPAL", "LA 21", "GLORIETA"}


async def test_compras_ordenadas_y_parte_de_la_sucursal(ctx, core_api):
    r = await correr(ctx, "recomendar_compras", sucursal="GLORIETA")
    assert core_api.params() == {"sucursal": "GLORIETA", "incluir_detalle": "false"}
    filas = r.para_modelo["filas"]
    assert [f["urgencia"] for f in filas] == ["urgente", "urgente"] and filas[0]["producto"] == "ARROZ CAROLINA *500 GR"
    assert filas[0]["para_sucursal"] == "8 unidades" and "toda la compra" in r.para_modelo["nota"]       # C16
    assert r.data["columnas"][3] == {"clave": "para_sucursal", "titulo": "Para GLORIETA", "tipo": "cantidad"}
    assert POR_NOMBRE["recomendar_compras"].lenta(None)


async def test_compras_del_admin_sucursal_y_kg(core):
    r = await correr(Contexto(core, "Bearer token-principal", "r"), "recomendar_compras")
    assert r.para_modelo["filtro"] == {"sucursal": "PRINCIPAL", "por_tu_rol": True}
    assert r.para_modelo["resumen"]["cantidad"] == "0 unidades y 120,0 kg"


async def test_compras_sin_sucursal(ctx):
    r = await correr(ctx, "recomendar_compras", urgencia="urgente", categoria="huevos")
    assert "nota" not in r.para_modelo and "para_sucursal" not in r.para_modelo["filas"][0]


def test_ninguna_herramienta_llama_a_ml_service():                                  # criterio 2, D12
    for h in CATALOGO:
        for _, ruta, _ in h.endpoints:
            assert ruta.startswith("/api/") and "8001" not in ruta and "ml_service" not in ruta
