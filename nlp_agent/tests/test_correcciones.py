"""Correcciones del 24-oct (§3g de docs/INV-33-requerimientos.md), cada una con su interruptor: C1 periodo, C2 y C3
categoría, C4 cobertura, C5 glosario, C6 meses, C7 relleno, C8 totales y C9 búsqueda. Sin el interruptor, nada cambia."""
import pytest

from agente.bucle import EjecutorCoreAPI, Resumen, responder
from agente.fidelidad import INICIO_GLOSARIO, cifras_no_respaldadas, respaldo_glosario
from agente.mejoras import Mejoras, corregir_argumentos, texto_usuario
from herramientas.catalogo import POR_NOMBRE, esquemas, rango_periodo, veredicto
from herramientas.contexto import (
    KILO,
    Contexto,
    contiene_todas,
    palabras,
    requiere_busqueda_por_palabras,
)
from herramientas.core_api import ErrorHerramienta
from tests.test_bucle import Guion


def _con(ctx: Contexto, **activas) -> Contexto:
    ctx.mejoras = Mejoras(**activas)
    return ctx


def _texto(pregunta: str) -> str:
    return texto_usuario([{"role": "user", "content": pregunta}])


# C1: periodo
def test_rango_del_periodo():
    assert rango_periodo("2025-11") == ("2025-11-01", "2025-11-30", "mes")
    assert rango_periodo("2025-T4") == ("2025-10-01", "2025-12-31", "mes")
    assert rango_periodo("2024") == ("2024-01-01", "2024-12-31", "trimestre")
    assert rango_periodo("2024-02")[1] == "2024-02-29"
    with pytest.raises(ErrorHerramienta, match="no es válido"):
        rango_periodo("noviembre")


def test_periodo_solo_con_su_interruptor():
    def propiedades(mejoras):
        return next(e for e in esquemas(mejoras) if e["function"]["name"] == "historial_ventas")["function"]["parameters"]["properties"]
    assert "periodo" not in propiedades(None) and "periodo" in propiedades(Mejoras(periodo=True))


async def test_historial_por_periodo(ctx, core_api):
    h = POR_NOMBRE["historial_ventas"]
    r = (await h.ejecutar(_con(ctx, periodo=True), h.validar({"categoria": "Lácteos", "periodo": "2025-11"}))).para_modelo
    params = core_api.params()
    assert (params["fecha_inicio"], params["fecha_fin"], params["agrupacion"]) == ("2025-11-01", "2025-11-30", "mes")
    assert r["periodo_pedido"] == "2025-11"


def test_anio_inventado_es_el_periodo():
    nuevos, correcciones = corregir_argumentos("historial_ventas", {"anio": 2025, "mes": "noviembre", "categoria": "x"},
                                               _texto("ventas de x en noviembre de 2025"), filtros=False, periodo=True)
    assert nuevos == {"categoria": "x", "periodo": "2025-11"} and "periodo=2025-11" in correcciones[0]


# C2 y C3: categoría
async def test_categoria_tolerante(ctx):
    with pytest.raises(ErrorHerramienta):
        await ctx.categoria("velas")
    assert await _con(ctx, categoria=True).categoria("velas") == "Velas y velones"
    assert await ctx.categoria("frutas") == "Frutas y verduras"


async def test_categoria_que_llega_como_producto(ctx, core_api):
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(_con(ctx, categoria=True), h.validar({"producto": "Lácteos"}))).para_modelo
    assert "es una categoría" in r["nota_categoria"] and core_api.params().get("categoria") == "Lácteos"
    huevos = (await h.ejecutar(ctx, h.validar({"producto": "huevos"}))).para_modelo          # hay productos con ese nombre
    assert "nota_categoria" not in huevos


# C4: cobertura
def test_veredicto_con_cifras():
    assert veredicto(618, 796, None, False, con_cifras=True) == \
        "no alcanza: hay 618 unidades y se esperan vender 796 unidades en 15 días hábiles; faltan 178 unidades para la demanda esperada"
    assert veredicto(618, 796, None, False) == "no alcanza: faltan 178 unidades para la demanda esperada"
    assert veredicto(26, 5, None, False, con_cifras=True).startswith("alcanza: hay 26 unidades")


def test_descripcion_del_pronostico_sin_anzuelo():
    def descripcion(mejoras):
        return next(e for e in esquemas(mejoras) if e["function"]["name"] == "pronosticar_demanda")["function"]["description"]
    assert "¿alcanza?" in descripcion(None) and "¿alcanza?" not in descripcion(Mejoras(cobertura=True))
    assert "producto concreto" in descripcion(Mejoras(cobertura=True))


# C5: glosario
GLOSARIO = [{"resultado": "encontrado", "total": 1, "fragmentos": [{
    "id": "cuantil_de_negocio", "titulo": "Cuantil de negocio", "fuente": "Glosario · Pronóstico (cuaderno 13)",
    "texto": "Qué es. El nivel de cuantil del pronóstico.\n\nEn el proyecto. Es 0,89 en los no perecederos.\n\nFuente. Cuaderno 13."}]}]


def test_porcentaje_de_un_cuantil():
    assert cifras_no_respaldadas("Se usa el 89 % en los no perecederos.", "", GLOSARIO) == []


def test_respaldo_del_glosario():
    texto = respaldo_glosario(GLOSARIO)
    assert texto.startswith(INICIO_GLOSARIO) and "Es 0,89 en los no perecederos." in texto and "Fuente: Glosario" in texto
    assert "Fuente. Cuaderno" not in texto and respaldo_glosario([{"total": 0}]) is None


async def test_bucle_respalda_con_el_glosario(ctx):
    llm = Guion([("buscar_en_glosario", {"consulta": "semáforo"})], "El semáforo tiene 7 colores y 99 reglas.",
                "El semáforo tiene 7 colores y 99 reglas.")
    mensajes = [{"role": "system", "content": "SISTEMA"}, {"role": "user", "content": "¿Qué es el semáforo?"}]
    r = Resumen()
    [e async for e in responder(llm, mensajes, EjecutorCoreAPI(ctx), r, verificar=True, mejoras=Mejoras(glosario=True))]
    assert r.respaldo and r.texto.startswith(INICIO_GLOSARIO)


# C6 y C7: la guarda
def test_meses_y_urgencia():
    texto = _texto("cuantas unidades de confiteria vendi en diciembre de 2025 y en noviembre")
    argumentos = {"categoria": "Confitería", "agrupacion": "mes", "dias": 61}
    assert corregir_argumentos("historial_ventas", argumentos, texto)[0] == {"categoria": "Confitería"}       # P1 sola
    assert corregir_argumentos("historial_ventas", argumentos, texto, meses=True)[0] == argumentos
    urgencia = _texto("Sugiereme los productos que debo comprar con urgencia")
    assert corregir_argumentos("recomendar_compras", {"urgencia": "urgente"}, urgencia, meses=True)[0] == {"urgencia": "urgente"}


def test_valores_de_relleno():
    nuevos, correcciones = corregir_argumentos(
        "recomendar_traslados", {"origen": "GLORIETA", "destino": ["PRINCIPAL", "LA 21"], "producto": "todos"},
        _texto("traslados de glorieta a principal"), relleno=True)
    assert nuevos == {"origen": "GLORIETA", "destino": "PRINCIPAL"} and len(correcciones) == 2


# C8: totales
async def test_stock_total_de_un_producto(ctx):
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(_con(ctx, totales=True), h.validar({"producto": "huevos *und"}))).para_modelo
    assert r["stock_total"] == "1.670 unidades en 3 ubicaciones"
    assert "stock_total" not in (await h.ejecutar(_con(ctx), h.validar({"producto": "huevos *und"}))).para_modelo


# C9: búsqueda
def test_busqueda_amplia():
    assert palabras("atún van camps de 3x80") == ["atun", "van", "camps", "3x80"]
    assert palabras("atún van camps de 3x80", amplia=True) == ["atun", "van", "camps", "3", "80"]
    assert palabras("sal refisal de kilo", amplia=True) == ["sal", "refisal", KILO]
    assert contiene_todas("ATUN VAN CAMPS AGUA 3*80", palabras("atun van camps 3x80", amplia=True))
    assert contiene_todas("SAL REFISAL *1000GR", palabras("sal refisal de kilo", amplia=True))
    assert not contiene_todas("SAL REFISAL 500GR", palabras("sal refisal de kilo", amplia=True))
    assert not requiere_busqueda_por_palabras("panela grande", ["PANELA GRANDE * 8"])
    assert requiere_busqueda_por_palabras("panela grande", ["PANELA GRANDE * 8"], amplia=True)
