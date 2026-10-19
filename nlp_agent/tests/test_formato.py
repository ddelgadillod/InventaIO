"""Cantidades como en la app (INV-32, criterio 4): los mismos casos de api/tests/test_textos_alertas.py."""
import pytest

from herramientas.formato import por_kilo, texto_cantidad, texto_dias, texto_numero


@pytest.mark.parametrize("valor, decimales, esperado", [
    (4024, 0, "4.024"), (-300, 0, "-300"), (1972.5, 1, "1.972,5"), (1234567.891, 2, "1.234.567,89"), (12.5, 0, "13"),
])
def test_numero_en_formato_es_co(valor, decimales, esperado):
    assert texto_numero(valor, decimales) == esperado


@pytest.mark.parametrize("valor, kg, esperado", [
    (-300, False, "-300 unidades"), (4024, False, "4.024 unidades"), (1, False, "1 unidad"), (-0.6, False, "-1 unidad"),
    (0.4, False, "0,4 unidades"), (0, False, "0 unidades"), (77.145, True, "77,1 kg"), (-0.04, True, "-0,04 kg"),
    (-0.01, True, "-0,01 kg"), (0, True, "0,0 kg"), (-2.05, True, "-2,1 kg"), (-1.25, True, "-1,3 kg"),
    (11.95, True, "12,0 kg"), (2.5, False, "3 unidades"), (0.5, False, "1 unidad"), (10.5, False, "11 unidades"),
    (3871.25, False, "3.871 unidades"),          # pronóstico de HUEVOS *UND en GLORIETA (C9)
])
def test_cantidad_segun_la_unidad_de_venta(valor, kg, esperado):
    assert texto_cantidad(valor, kg) == esperado


def test_dias_y_unidad():
    assert [texto_dias(0), texto_dias(5.3), texto_dias(5.25)] == ["0,0 d", "5,3 d", "5,3 d"]
    assert por_kilo("kg") and not por_kilo("unidad") and not por_kilo(None)
