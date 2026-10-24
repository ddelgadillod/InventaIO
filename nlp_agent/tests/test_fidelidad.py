"""Verificador de la respuesta (INV-33, Z4 y Z12): cifras, total y fecha, con los formatos de la app."""
import pytest

from agente.fidelidad import (
    cifras_no_respaldadas,
    dice_la_fecha,
    totales_omitidos,
    verificar,
)

INVENTARIO = {"fecha_dato": "2025-12-31", "total": 147, "mostrando": 10,
              "conteo": "147 filas de inventario en total; se muestran los primeros 10.",
              "filas": [{"producto": "HUEVOS *UND", "stock": "3.366 unidades"}, {"producto": "PAPAYA *KL", "stock": "1,5 kg"},
                        {"producto": "QUESO *KL", "stock": "1.250,5 kg"}]}


@pytest.mark.parametrize("texto", ["Hay 3366 huevos", "Hay 3.366 huevos", "Quedan 1,5 kg de papaya", "1.250,5 kg de queso",
                                   "Son 147 productos; te muestro 10"])
def test_formatos_respaldados(texto):
    assert cifras_no_respaldadas(texto, "¿inventario?", [INVENTARIO]) == []


@pytest.mark.parametrize("texto, fuera", [("Hay 3.400 huevos", ["3.400"]), ("Quedan 2,5 kg de papaya", []),
                                          ("Quedan 12,5 kg", ["12,5"])])
def test_cifras_sin_respaldo(texto, fuera):
    # 2,5 es un número pequeño (≤ 10): se ignora, como un conteo
    assert cifras_no_respaldadas(texto, "¿inventario?", [INVENTARIO]) == fuera


def test_el_total_de_una_lista_recortada():
    assert totales_omitidos("Estos son 10 productos críticos: …", [INVENTARIO]) == [147]
    assert totales_omitidos("Hay 147 productos críticos; estos son los 10 primeros", [INVENTARIO]) == []
    assert totales_omitidos("Hay 3 productos", [{"total": 3, "mostrando": 3, "filas": []}]) == []


@pytest.mark.parametrize("texto, dice", [("Datos al 31 de diciembre de 2025.", True), ("al 31 de diciembre", True),
                                         ("foto del 2025-12-31", True), ("corte 31/12/2025", True), ("Hay 3.366 huevos", False)])
def test_la_fecha(texto, dice):
    assert dice_la_fecha(texto, "2025-12-31") is dice


def test_verificar_y_lo_que_se_pide_corregir():
    v = verificar("Hay 3.400 huevos entre 10 productos", "¿huevos?", [INVENTARIO])
    assert not v.ok and v.cifras_sin_respaldo == ["3.400"] and v.totales_omitidos == [147]
    assert v.correccion() == ("Corrige tu respuesta: estas cifras no están en los datos consultados: 3.400; usa solo las "
                              "cifras de los resultados; di el total de los resultados (147) y que muestras solo una parte.")
    assert v.cierre() == "Datos al 31 de diciembre de 2025."
    ok = verificar("Hay 147 productos; HUEVOS tiene 3.366 unidades. Datos al 31 de diciembre de 2025.", "", [INVENTARIO])
    assert ok.ok and ok.fecha is None and ok.correccion() == "" and ok.cierre() == ""


def test_sin_herramientas_no_hay_fecha_que_agregar():
    assert verificar("¡Hola! ¿En qué te ayudo?", "hola", []).cierre() == ""


def test_multiturno_cifra_imitada_del_turno_anterior():
    """Caso reproducido el 21-oct con temperatura 0 (prompt v1): tras «En GLORIETA hay 173 productos en estado
    crítico.», a «¿Y en LA 21?» el modelo responde sin herramientas «hay 125» (son 147). El 173 está en la
    conversación; el 125 no está en ninguna parte: pide reintento."""
    conversacion = "¿Qué hay crítico en GLORIETA?\nEn GLORIETA hay 173 productos en estado crítico.\n¿Y en LA 21?"
    v = verificar("En LA 21 hay 125 productos en estado crítico.", conversacion, [])
    assert not v.ok and v.cifras_sin_respaldo == ["125"]
    assert verificar("En GLORIETA había 173.", conversacion, []).ok


def test_el_nombre_del_campo_respalda_su_cifra():
    """22-oct, v1-02: «ventas de 10 unidades en los últimos 30 días» con el campo ventas_30d."""
    r = {"filas": [{"producto": "PONQUE BIMBO CASERO *240GR", "ventas_30d": "10 unidades"}], "total": 1}
    assert cifras_no_respaldadas("Vendió 10 unidades en los últimos 30 días", "", [r]) == []


def test_sin_consultar_pide_consultar():
    """22-oct, v1-24: cifras inventadas sin ninguna herramienta; la corrección pide consultar."""
    v = verificar("ventas_totales: 1.234.567,89", "dame un reporte de ventas", [])
    assert v.sin_consultar and "sin consultar ninguna herramienta" in v.correccion()
