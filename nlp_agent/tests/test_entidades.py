"""Alternativa 1 (24-oct): las entidades de la pregunta (sucursal, categoría, periodo), detectadas con datos del
catálogo, se le entregan al modelo y completan lo que omita. No cambia el esquema."""
from datetime import date

from agente.bucle import EjecutorCoreAPI, Resumen, responder
from agente.entidades import completar, detectar
from agente.mejoras import Mejoras
from tests.test_bucle import Guion


def _mensajes(*preguntas):
    salida = [{"role": "system", "content": "SISTEMA"}]
    for i, p in enumerate(preguntas):
        if i:
            salida.append({"role": "assistant", "content": "…"})
        salida.append({"role": "user", "content": p})
    return salida


async def test_detecta_sucursal_categoria_y_periodo(ctx):
    e = await detectar(_mensajes("¿Cuánto vendimos de lácteos en noviembre de 2025 en GLORIETA?"), ctx)
    assert e.sucursales == ["GLORIETA"] and e.categorias == ["Lácteos"]
    assert (e.periodo.fila, e.periodo.desde, e.periodo.hasta) == ("2025-11", date(2025, 11, 1), date(2025, 11, 30))
    assert "fila 2025-11" in e.mensaje() and "va en el filtro categoria" in e.mensaje()


async def test_un_producto_no_es_su_categoria(ctx):
    e = await detectar(_mensajes("¿Cuánto arroz carolina hay?"), ctx)
    assert e.categorias == []                                  # «arroz carolina» es un producto, no la categoría Arroz
    assert (await detectar(_mensajes("ventas de arroz por trimestre"), ctx)).categorias == ["Arroz"]


async def test_el_periodo_toma_el_año_de_la_conversacion(ctx):
    e = await detectar(_mensajes("¿cuántos lácteos vendí en diciembre de 2025?", "¿y en noviembre?"), ctx)
    assert e.periodo.fila == "2025-11" and e.categorias == ["Lácteos"]


async def test_direccion_del_traslado(ctx):
    assert (await detectar(_mensajes("¿Qué debo mover hoy a la 21?"), ctx)).direccion == {"LA 21": "destino"}
    assert (await detectar(_mensajes("traslados desde glorieta"), ctx)).direccion == {"GLORIETA": "origen"}


async def test_completar(ctx):
    e = await detectar(_mensajes("¿Cuánto vendimos de lácteos en noviembre de 2025 en GLORIETA?"), ctx)
    nuevos, hecho = completar("historial_ventas", {}, e, date(2025, 12, 31))
    assert nuevos == {"categoria": "Lácteos", "dias": 61, "agrupacion": "mes", "sucursal": "GLORIETA"} and len(hecho) == 3
    assert completar("historial_ventas", {"producto": "leche"}, e, None)[0] == {"producto": "leche", "sucursal": "GLORIETA"}
    destino = await detectar(_mensajes("¿Qué debo mover hoy a la 21?"), ctx)
    assert completar("recomendar_traslados", {}, destino, None)[0] == {"destino": "LA 21"}


async def test_bucle_entrega_y_completa(ctx):
    llm = Guion([("historial_ventas", {"categoria": "Lácteos"})], "En noviembre de 2025 se vendieron 120 unidades.")
    mensajes = _mensajes("¿Cuánto vendimos de lácteos en noviembre de 2025?")
    r = Resumen()
    [x async for x in responder(llm, mensajes, EjecutorCoreAPI(ctx), r, mejoras=Mejoras(entidades=True))]
    enviados = llm.recibidos[0][0]
    assert enviados[1]["role"] == "system" and enviados[1]["content"].startswith("Datos detectados") and enviados[2]["role"] == "user"
    assert r.entidades and r.ejecutadas[0]["argumentos"]["agrupacion"] == "mes" and r.ejecutadas[0]["argumentos"]["dias"] > 30


async def test_sin_el_interruptor_nada_cambia(ctx):
    llm = Guion([("historial_ventas", {"categoria": "Lácteos"})], "Listo.")
    r = Resumen()
    [x async for x in responder(llm, _mensajes("ventas de lácteos en noviembre de 2025"), EjecutorCoreAPI(ctx), r)]
    assert r.entidades == "" and [m["role"] for m in llm.recibidos[0][0]] == ["system", "user"]
