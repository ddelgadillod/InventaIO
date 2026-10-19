"""Resolución de nombres (INV-32, T2, C4, C5, C18, C19) con el Core API simulado."""
import pytest

from herramientas.contexto import (
    Candidatos,
    Contexto,
    Producto,
    _ordenar,
    contiene_todas,
    normal,
    palabras,
)
from herramientas.core_api import ErrorHerramienta


def test_normal_y_palabras():
    assert normal("  Lácteos ") == "lacteos" and normal("ARROZ CAROLINA *500 GR") == "arroz carolina 500 gr"
    assert palabras("arroz Carolina x 500 gramos") == ["arroz", "carolina", "500"]
    assert contiene_todas("ARROZ CAROLINA *500 GR", ["carolina", "500"])
    assert not contiene_todas("ARROZ CAROLINA *5000 GR", ["carolina", "500"])     # el número va completo
    assert contiene_todas("ARROZ BETARROZ *500GR", ["500"])


@pytest.mark.parametrize("texto, codigo", [
    ("P1632", "P1632"),                          # código exacto
    ("huevos *und", "P1632"),                    # nombre exacto, sin mayúsculas
    ("betarroz", "00805"),                       # una sola coincidencia
    ("arroz carolina x 500 gramos", "P618"),     # la frase no es subcadena: todas las palabras (C4)
])
async def test_producto_resuelto(ctx, texto, codigo):
    p = await ctx.producto(texto)
    assert isinstance(p, Producto) and p.codigo == codigo


async def test_producto_ambiguo_con_candidatos_ordenados(ctx):
    r = await ctx.producto("arroz carolina")
    assert isinstance(r, Candidatos) and (r.estado, r.total) == ("ambiguo", 4)
    assert [p.nombre for p in r.candidatos] == ["ARROZ CAROLINA *500 GR", "ARROZ CAROLINA *1000 GR",
                                                "ARROZ CAROLINA *3000 GR", "ARROZ CAROLINA *5000 GR"]
    d = r.para_modelo()
    assert d["resultado"] == "ambiguo" and len(d["candidatos"]) == 4 and "pide al usuario" in d["indicacion"]


async def test_leche_ambiguo_y_el_mas_corto_primero(ctx):
    r = await ctx.producto("leche")
    assert r.estado == "ambiguo" and r.total == 2
    assert r.candidatos[0].nombre == "CAFE CON LECHE COLCAFE *22GR *6 UND"   # ninguno empieza por «leche»


def test_orden_codigo_nombre_y_comienzo():
    def prod(codigo, nombre):
        return Producto(1, codigo, nombre, "Lácteos", "unidad")
    lista = [prod("P3833", "ARROZ CON LECHE ROA TRADICIONAL * 150GR"), prod("P1", "LECHE ENTERA *1100ML"),
             prod("P2", "LECHE"), prod("LECHE", "OTRO")]
    assert [p.codigo for p in _ordenar(lista, "leche")] == ["LECHE", "P2", "P1", "P3833"]


async def test_producto_no_encontrado(ctx):
    r = await ctx.producto("zzzz")
    assert r.estado == "no_encontrado" and r.para_modelo()["total"] == 0


@pytest.mark.parametrize("texto, canonica", [("arroz", "Arroz"), ("lacteos", "Lácteos"), ("lácteo", "Lácteos"),
                                             ("FRUTAS Y VERDURAS", "Frutas y verduras")])
async def test_categoria_canonica(ctx, texto, canonica):
    assert await ctx.categoria(texto) == canonica


async def test_categoria_desconocida(ctx, core_api):
    with pytest.raises(ErrorHerramienta) as e:
        await ctx.categoria("juguetes")
    assert e.value.status == 422 and "Arroz" in e.value.mensaje
    await ctx.categoria("arroz")
    assert core_api.rutas().count("/api/consulta/categorias") == 1      # una vez por pregunta


async def test_sucursales_con_ids_del_core_api(ctx, core_api):
    assert (await ctx.sucursal("glorieta")).id == 3 and (await ctx.sucursal("BODEGA_CENTRAL")).fisica is False
    with pytest.raises(ErrorHerramienta):
        await ctx.sucursal("CENTRO")
    assert core_api.rutas().count("/api/consulta/sucursales") == 1


@pytest.mark.parametrize("token, tiendas", [
    ("Bearer token-de-prueba", ["PRINCIPAL", "LA 21", "GLORIETA"]),
    ("Bearer token-bodega", ["PRINCIPAL", "LA 21", "GLORIETA"]),       # T9: el admin_bodega, como el gerente
    ("Bearer token-la21", ["LA 21"]),
])
async def test_tiendas_por_rol(core, token, tiendas):
    assert await Contexto(core, token, "r").tiendas_por_rol() == tiendas


async def test_el_perfil_descarta_email_y_nombre(ctx):
    perfil = await ctx.perfil()
    assert vars(perfil) == {"rol": "gerente", "sucursal": None}          # C18


async def test_sin_sucursal_fisica(core, monkeypatch):
    from tests import core_falso
    monkeypatch.setitem(core_falso.PERFILES, "Bearer token-raro", ("admin_sucursal", "BODEGA_CENTRAL"))
    with pytest.raises(ErrorHerramienta) as e:
        await Contexto(core, "Bearer token-raro", "r").tiendas_por_rol()
    assert e.value.status == 403
