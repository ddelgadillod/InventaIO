"""Mejoras del desempeño de INV-33 (§3f, 23-oct): la guarda de argumentos (P1, P6), la aclaración armada (P2),
la regla de «sin datos» (P3), seguir cuando el modelo ofrece (P4), la cobertura en el pronóstico (P5), los
traslados por destino u origen (P6) y el razonamiento en el reintento (P7). Los ejemplos vienen del v1 (el
conjunto de desarrollo), nunca de los holdouts."""
import json

import pytest

from agente.bucle import EjecutorCoreAPI, Resumen, responder
from agente.fidelidad import sin_datos_con_contenido, verificar
from agente.mejoras import (
    Mejoras,
    aclaracion,
    corregir_argumentos,
    ofrece_consultar,
    sin_repetidas,
    texto_usuario,
)
from evaluacion.conjunto import Esperado, a_legado, coincide
from herramientas.catalogo import POR_NOMBRE, nombra_presentacion, veredicto
from tests.test_bucle import Guion

TODAS = Mejoras.desde_texto("todas")


def _texto(pregunta: str) -> str:
    return texto_usuario([{"role": "user", "content": pregunta}])


def test_interruptores():
    assert TODAS.como_texto() == "argumentos,agrupacion,aclaracion,sin_datos,seguir" and not TODAS.razonar
    assert Mejoras.desde_texto("ninguna") == Mejoras() == Mejoras.desde_texto("")
    assert Mejoras.desde_texto("aclaracion, razonar") == Mejoras(aclaracion=True, razonar=True)
    with pytest.raises(ValueError, match="desconocidas: magia"):
        Mejoras.desde_texto("magia")


@pytest.mark.parametrize("pregunta, herramienta, argumentos, quedan", [
    # v1-19 y v1-20: urgencia y sucursal que nadie pidió
    ("Dame un pedido sugerido para productos de aseo hogar en la 21", "recomendar_compras",
     {"categoria": "aseo hogar", "sucursal": "LA 21", "urgencia": "normal"}, {"categoria": "aseo hogar", "sucursal": "LA 21"}),
    ("Dame el sugerido de pedidos a proveedor", "recomendar_compras", {"urgencia": "normal", "sucursal": "GLORIETA"}, {}),
    # v1-45: tipo, origen y sucursal inventados; el producto se queda
    ("Que aelrtas para Jabon tenemos", "listar_alertas",
     {"tipo": "inconsistencia_inventario", "origen": "reglas", "sucursal": "PRINCIPAL", "producto": "Jabon"}, {"producto": "Jabon"}),
    # lo que sí se pidió, con sus sinónimos, no se toca
    ("Que recomendaciones de traslados hay y que sean prioritarias", "recomendar_traslados", {"urgencia": "urgente"}, {"urgencia": "urgente"}),
    ("¿Qué productos se van a agotar según la IA?", "listar_alertas", {"origen": "ia"}, {"origen": "ia"}),
    ("Lista los traslados de glorieta a demas sucursales", "recomendar_traslados", {"origen": "GLORIETA"}, {"origen": "GLORIETA"}),
    ("¿Cuánto arroz hay en la bodega?", "consultar_inventario", {"producto": "arroz", "sucursal": "BODEGA_CENTRAL"},
     {"producto": "arroz", "sucursal": "BODEGA_CENTRAL"}),
    ("¿Cuánto vendimos los últimos 90 días?", "historial_ventas", {"dias": 90}, {"dias": 90}),
    ("Productos de licor en la 21", "consultar_inventario", {"categoria": "Licores", "sucursal": "LA 21"},
     {"categoria": "Licores", "sucursal": "LA 21"}),
])
def test_guarda_de_argumentos(pregunta, herramienta, argumentos, quedan):
    nuevos, correcciones = corregir_argumentos(herramienta, argumentos, _texto(pregunta))
    assert nuevos == quedan and len(correcciones) == len(argumentos) - len(quedan)


def test_agrupacion_del_historico():
    """P6 (v1-09): «histórico» sin periodo es por año; sin la mejora, no se toca."""
    texto = _texto("Dame un reporte del historico de ventas de Arroz Diana * 500")
    nuevos, correcciones = corregir_argumentos("historial_ventas", {"producto": "Arroz Diana * 500"}, texto, agrupacion=True)
    assert nuevos["agrupacion"] == "anio" and "histórico" in correcciones[0]
    assert corregir_argumentos("historial_ventas", {"producto": "x"}, texto)[1] == []
    trimestral = _texto("ventas por trimestre de los años anteriores")
    assert corregir_argumentos("historial_ventas", {}, trimestral, agrupacion=True)[0] == {"agrupacion": "trimestre"}


def test_los_mensajes_automaticos_no_cuentan():
    mensajes = [{"role": "user", "content": "Dame el sugerido de pedidos"},
                {"role": "user", "content": "(Verificación automática) di el total de las urgentes"}]
    assert "urgent" not in texto_usuario(mensajes)


def test_llamadas_repetidas():
    quedan, quitadas = sin_repetidas([("resumen_alertas", {}), ("resumen_alertas", {"sucursal": None}), ("resumen_alertas", {})])
    assert quedan == [0] and quitadas == 2


def test_aclaracion_armada():
    ambiguo = {"resultado": "ambiguo", "busqueda": "jabon rey", "total": 7,
               "candidatos": [{"codigo": f"P{i}", "nombre": f"JAB REY {i}", "categoria": "Aseo hogar"} for i in range(5)]}
    texto = aclaracion([ambiguo, {"error": {"status": 422}}])
    assert texto.startswith("Hay 7 productos que coinciden con «jabon rey». ¿Cuál de ellos?")
    assert "- JAB REY 0 (código P0)" in texto and "dime el nombre completo o el código" in texto
    assert aclaracion([ambiguo, {"total": 3, "filas": []}]) is None                # con datos, decide el modelo
    assert aclaracion([{"total": 0, "filas": []}]) is None


@pytest.mark.parametrize("texto, sigue", [
    ("El código corresponde a JAB REY. ¿Te gustaría ver el historial de ventas de este producto?", True),
    ("Para saberlo necesito el inventario. ¿Quieres que consulte estos datos?", True),
    ("El pronóstico es de 5. ¿Quieres que te ayude a verificar el inventario actual?", True),
    ("Hay 242 líneas. ¿Quieres ver más o necesitas información de algún producto?", False),
    ("¿Necesitas más detalles o un periodo específico?", False),
    ("¿Cuál de estos productos te refieres?", False),
    ("¿Te gustaría ver el historial? Datos al 31 de diciembre de 2025.", False),           # no termina ofreciendo
])
def test_ofrece_consultar(texto, sigue):
    assert ofrece_consultar(texto) is sigue


def test_sin_datos_con_contenido():
    vacio = [{"resultado": "sin_resultados", "consulta": "rotación ABC"}]
    assert sin_datos_con_contenido("La rotación ABC clasifica los productos por su valor.", vacio)
    assert not sin_datos_con_contenido("El glosario no tiene información sobre la rotación ABC.", vacio)
    assert not sin_datos_con_contenido("Hay 3.", [{"total": 3, "filas": [{"x": 1}]}])
    v = verificar("La rotación ABC clasifica los productos.", "", vacio, sin_datos=True)
    assert not v.ok and "no trajeron información" in v.correccion()
    assert verificar("La rotación ABC clasifica los productos.", "", vacio).ok        # sin la mejora, no se revisa


def test_veredicto_de_cobertura():
    assert veredicto(26, 5, None, False) == "alcanza"
    assert veredicto(126, 305.4, None, False).startswith("no alcanza: faltan 179")
    assert "por debajo de la cobertura recomendada (209" in veredicto(166, 72, {"limite_superior": 209}, False)
    assert veredicto(10, 72, {"limite_superior": 5}, False).startswith("no alcanza")
    assert "negativo" in veredicto(-44, 3, None, False) and "sin registro" in veredicto(None, 3, None, False)


def test_presentacion():
    assert nombra_presentacion("Leche Colanta * 1100") and nombra_presentacion("arroz 500")
    assert not nombra_presentacion("jabones") and not nombra_presentacion("P1234")


def test_legado_de_traslados():
    """P6: el calificador traduce destino/origen a la forma congelada en el v1 y en el holdout."""
    viejo = Esperado(herramienta="recomendar_traslados", argumentos={"sucursal": "PRINCIPAL"}, opcionales={"direccion": "hacia"})
    assert coincide(viejo, "recomendar_traslados", {"destino": "PRINCIPAL"})
    assert not coincide(viejo, "recomendar_traslados", {"origen": "PRINCIPAL"})
    assert a_legado("recomendar_traslados", {"origen": "GLORIETA", "urgencia": "alta"}) == \
        {"urgencia": "alta", "sucursal": "GLORIETA", "direccion": "desde"}
    assert a_legado("consultar_inventario", {"destino": "x"}) == {"destino": "x"}


async def test_inventario_ambiguo_si_nombra_presentacion(ctx):
    """Decisión del 23-oct: «arroz 500» coincide con dos productos de 500 g; «arroz» genérico sigue listando."""
    h = POR_NOMBRE["consultar_inventario"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "arroz 500"}))).para_modelo
    assert r["resultado"] == "ambiguo" and {c["codigo"] for c in r["candidatos"]} >= {"P618", "00805"}
    generico = (await h.ejecutar(ctx, h.validar({"producto": "arroz"}))).para_modelo
    assert "resultado" not in generico and generico["total"] >= 2


async def test_pronostico_con_stock_y_veredicto(ctx):
    h = POR_NOMBRE["pronosticar_demanda"]
    r = (await h.ejecutar(ctx, h.validar({"producto": "huevos *und"}))).para_modelo
    glorieta = next(f for f in r["filas"] if f["sucursal"] == "GLORIETA")
    assert glorieta["stock"] == "420 unidades" and glorieta["veredicto"].startswith("no alcanza: faltan")


async def _correr(llm, ctx, pregunta, mejoras=TODAS, verificar_=True):
    mensajes = [{"role": "system", "content": "SISTEMA"}, {"role": "user", "content": pregunta}]
    r = Resumen()
    eventos = [e async for e in responder(llm, mensajes, EjecutorCoreAPI(ctx), r, request_id="req-1",
                                          verificar=verificar_, mejoras=mejoras)]
    return eventos, r, mensajes


async def test_bucle_guarda_y_repetidas(ctx):
    """P1: tres resúmenes, uno por sucursal que nadie nombró, se ejecutan como uno solo y sin filtros."""
    llm = Guion([("resumen_alertas", {"sucursal": "PRINCIPAL"}), ("resumen_alertas", {"sucursal": "LA 21"}),
                 ("resumen_alertas", {"sucursal": "GLORIETA"})], "Hay 4.452 alertas: 1.334 críticas.")
    _, r, mensajes = await _correr(llm, ctx, "Dame un reporte general de las alertas por nivel")
    assert [ll["argumentos"] for ll in r.llamadas] == [{"sucursal": s} for s in ("PRINCIPAL", "LA 21", "GLORIETA")]
    assert r.ejecutadas == [{"ronda": 1, "herramienta": "resumen_alertas", "argumentos": {}}]
    assert len(r.resultados) == 1 and "Se quitó sucursal=PRINCIPAL" in r.resultados[0]["nota_guarda"]
    assert "2 llamada(s) repetida(s)" in r.correcciones
    assert mensajes[2]["tool_calls"] == [{"function": {"name": "resumen_alertas", "arguments": {}}}]


async def test_bucle_sin_mejoras_no_corrige(ctx):
    llm = Guion([("resumen_alertas", {"sucursal": "PRINCIPAL"})], "Listo.")
    _, r, _ = await _correr(llm, ctx, "Dame un reporte general de las alertas", mejoras=Mejoras())
    assert r.ejecutadas == [{"ronda": 1, "herramienta": "resumen_alertas", "argumentos": {"sucursal": "PRINCIPAL"}}]
    assert r.correcciones == []


async def test_bucle_aclaracion_sin_pasar_por_el_modelo(ctx):
    """P2: el pronóstico responde «ambiguo» y el bucle pregunta, con las opciones; el modelo no vuelve a hablar."""
    llm = Guion([("pronosticar_demanda", {"producto": "arroz carolina"})])
    eventos, r, _ = await _correr(llm, ctx, "¿Cuánto arroz carolina se va a vender?")
    assert r.aclaracion and len(llm.recibidos) == 1 and r.fidelidad == "ok"
    assert "¿Cuál de ellos?" in r.texto and "ARROZ CAROLINA *500 GR (código P618)" in r.texto
    assert [e for e, _ in eventos if e != "tool"] and all(e in ("tool", "token") for e, _ in eventos)


async def test_bucle_sin_datos_reintenta(ctx):
    """P3: el glosario no trae nada y la respuesta afirma contenido: se reintenta y la segunda lo dice."""
    llm = Guion([("buscar_en_glosario", {"consulta": "zzz qqq inexistente"})],
                "La rotación zzz clasifica los productos por su margen.",
                "El glosario no tiene información sobre eso. Puedo consultar el inventario.")
    _, r, mensajes = await _correr(llm, ctx, "¿Qué es la rotación zzz qqq inexistente?")
    assert r.resultados[0]["resultado"] == "sin_resultados" and r.fidelidad == "reintento"
    assert "no trajeron información" in mensajes[-1]["content"] and r.texto.startswith("El glosario no tiene")


async def test_bucle_sigue_cuando_ofrece(ctx):
    """P4: «¿Te gustaría ver …?» con rondas libres: el bucle contesta que sí y el modelo consulta."""
    llm = Guion([("buscar_producto", {"texto": "P1632"})],
                "El código P1632 es HUEVOS *UND. ¿Te gustaría ver el inventario de este producto?",
                [("consultar_inventario", {"producto": "HUEVOS *UND"})],
                "Hay 420 en GLORIETA y 1.250 en PRINCIPAL.")
    _, r, mensajes = await _correr(llm, ctx, "¿A qué corresponde el P1632 y cuánto hay?")
    assert r.seguida and r.texto.startswith("Hay 420 en GLORIETA")
    assert any(m.get("content", "").startswith("(Continuación automática)") for m in mensajes)
    assert [ll["herramienta"] for ll in r.ejecutadas] == ["buscar_producto", "consultar_inventario"]


class GuionRazonar(Guion):
    async def chat_stream(self, mensajes, opciones=None, herramientas=None, razonar=None):
        self.razonar = getattr(self, "razonar", []) + [razonar]
        async for f in super().chat_stream(mensajes, opciones, herramientas):
            yield f


async def test_bucle_razona_solo_en_el_reintento(ctx):
    """P7: la ronda del reintento del verificador va con razonamiento; las demás, con la configuración."""
    llm = GuionRazonar([("consultar_inventario", {"producto": "huevos"})], "Hay 999 huevos.", "Hay 420 en GLORIETA.")
    _, r, _ = await _correr(llm, ctx, "¿Cuántos huevos hay?", mejoras=Mejoras(razonar=True))
    assert llm.razonar == [None, None, True] and r.fidelidad == "reintento"


def test_el_esquema_de_traslados():
    propiedades = POR_NOMBRE["recomendar_traslados"].esquema()["function"]["parameters"]["properties"]
    assert {"destino", "origen"} <= set(propiedades) and not {"sucursal", "direccion"} & set(propiedades)
    assert json.dumps(propiedades, ensure_ascii=False).count("BODEGA_CENTRAL") >= 2
