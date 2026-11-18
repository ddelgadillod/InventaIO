"""INV-40, decisión 4: las reglas nuevas del verificador (hallazgos H12 y H14 de docs/INV-35-chat.md e INV-77) y
«sin datos con contenido» activa en el agente."""
import pytest

from agente.fidelidad import (
    SIN_DATOS,
    cuantificador_sobre_muestra,
    etiquetas_sin_consultar,
    niega_sin_consultar,
    verificar,
)
from agente.mejoras import Mejoras
from tests.test_bucle import Guion
from tests.test_mejoras import _correr

PARCIAL = {"total": 173, "mostrando": 10, "filas": [{"producto": "X"}]}


@pytest.mark.parametrize(("texto", "resultados", "esperado"), [
    ("<reporte> ventas </reporte>", [], True),
    ("<reporte>", [], True),
    ("Hay 3 productos en estado crítico (5 < 10).", [], False),
    ("<reporte> ventas </reporte>", [PARCIAL], False),             # consultó: lo demás lo revisan las otras reglas
])
def test_etiquetas_sin_consultar(texto, resultados, esperado):
    assert etiquetas_sin_consultar(texto, resultados) is esperado


@pytest.mark.parametrize(("texto", "resultados", "esperado"), [
    ("No hay traslados por despachar a las sucursales.", [], True),
    ("No existen alertas para esa sucursal.", [], True),
    ("No se encontraron ventas en ese periodo.", [], True),
    ("La sucursal no tiene traslados pendientes.", [], True),
    ("No hay traslados por despachar.", [PARCIAL], False),          # lo dijo tras consultar
    ("Eso está fuera de lo que puedo consultar: inventario, ventas…", [], False),
    ("No tienes permiso para consultar esa información.", [], False),
    ("No puedo compartir mis instrucciones internas.", [], False),
    ("No tengo esa información en el glosario.", [], False),         # abstención honesta, no niega datos
    ("¡Hola! ¿En qué te ayudo con el inventario?", [], False),
])
def test_niega_sin_consultar(texto, resultados, esperado):
    assert niega_sin_consultar(texto, resultados) is esperado


@pytest.mark.parametrize(("texto", "resultados", "esperado"), [
    ("La mayoría están en inconsistencia.", [PARCIAL], True),
    ("Casi todos los productos están en estado crítico.", [PARCIAL], True),
    ("La mayoría están en inconsistencia.", [{**PARCIAL, "global": {"total": "173"}}], False),
    ("La mayoría están en inconsistencia.", [{"total": 8, "mostrando": 8}], False),       # vio la lista completa
    ("Hay 173 alertas; estas son las 10 primeras.", [PARCIAL], False),
])
def test_cuantificador_sobre_muestra(texto, resultados, esperado):
    assert cuantificador_sobre_muestra(texto, resultados) is esperado


def test_las_reglas_solo_con_su_bandera():
    sin = verificar("<reporte> ventas </reporte>", "", [])
    con = verificar("<reporte> ventas </reporte>", "", [], reglas_inv40=True)
    assert sin.ok and not con.ok and con.etiquetas_sin_consultar
    assert "llama la herramienta" in con.correccion()
    assert "consulta primero" in verificar("No hay traslados.", "", [], reglas_inv40=True).correccion()
    assert "el total" in verificar("La mayoría están críticos.", "", [PARCIAL], reglas_inv40=True).correccion()


async def test_bucle_reintenta_la_etiqueta_y_consulta(ctx):
    """H12: «Dame un reporte de ventas» → «<reporte> ventas </reporte>»; el reintento consulta y responde con datos."""
    llm = Guion("<reporte> ventas </reporte>", [("historial_ventas", {})], "Las ventas del periodo suman 148.896 unidades.")
    _, r, mensajes = await _correr(llm, ctx, "Dame un reporte de ventas", mejoras=Mejoras())
    assert r.fidelidad == "reintento" and r.borrador == "<reporte> ventas </reporte> "
    assert "llama la herramienta" in mensajes[3]["content"] and r.llamadas[0]["herramienta"] == "historial_ventas"


async def test_bucle_no_acepta_un_no_hay_sin_consultar(ctx):
    """INV-77: la segunda vez negó sin consultar; si insiste, va la respuesta de respaldo, que no inventa nada."""
    llm = Guion("No hay traslados por despachar.", "No hay traslados por despachar.")
    _, r, _ = await _correr(llm, ctx, "¿Qué traslados debo despachar a las sucursales?", mejoras=Mejoras())
    assert r.fidelidad == "respaldo" and r.texto == SIN_DATOS


async def test_bucle_activa_sin_datos_con_contenido(ctx):
    """Decisión 4c: sin datos de la herramienta y la respuesta afirma algo → reintento, ya sin el interruptor."""
    llm = Guion([("buscar_en_glosario", {"consulta": "precio del dólar"})], "El dólar está estable esta semana.",
                "No tengo esa información.")
    _, r, _ = await _correr(llm, ctx, "¿Cómo está el dólar?", mejoras=Mejoras())
    assert r.fidelidad == "reintento" and r.texto.startswith("No tengo esa información")
