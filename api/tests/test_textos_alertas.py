"""INV-26 fix (validación de pantallas, A12) — Cantidades y días en los textos de
las alertas como los muestra la app: unidad de venta en singular o plural, punto
de miles, coma decimal, el mismo redondeo que fmtCantidad (formato.test.js tiene
los mismos casos) y ninguna cantidad distinta de 0 redondeada a 0 (antes
"(-0 uds)" en productos por kilo). Sin base."""
import pytest

from core.productos import texto_cantidad, texto_dias, texto_numero


@pytest.mark.parametrize("valor, decimales, esperado", [
    (4024, 0, "4.024"), (-300, 0, "-300"), (1972.5, 1, "1.972,5"), (1234567.891, 2, "1.234.567,89"),
    (12.5, 0, "13"),                      # porcentaje de rotación baja: antes "12" (empate al par)
])
def test_numero_en_formato_es_co(valor, decimales, esperado):
    assert texto_numero(valor, decimales) == esperado


@pytest.mark.parametrize("valor, por_kilo, esperado", [
    (-300, False, "-300 unidades"),       # AZUCAR MORENA MANUELITA *1KG, se vende por unidad
    (4024, False, "4.024 unidades"),
    (1, False, "1 unidad"),               # antes "1 uds" en 906 alertas
    (-0.6, False, "-1 unidad"),           # se ve "-1", como en la app
    (0.4, False, "0,4 unidades"),
    (0, False, "0 unidades"),
    (77.145, True, "77,1 kg"),            # PAPA PASTUSA *KL en PRINCIPAL
    (-0.04, True, "-0,04 kg"),            # UVA VERDE CIDRA en GLORIETA: antes "-0 uds"
    (-0.01, True, "-0,01 kg"),            # CHICHARRON LAFAZENDA KL en PRINCIPAL
    (0, True, "0,0 kg"),
])
def test_cantidad_segun_la_unidad_de_venta(valor, por_kilo, esperado):
    assert texto_cantidad(valor, por_kilo) == esperado


@pytest.mark.parametrize("valor, por_kilo, esperado", [
    (-2.05, True, "-2,1 kg"),             # MANDARINA *KL en PRINCIPAL: la alerta decía "-2,0" y la app "-2,1"
    (-1.25, True, "-1,3 kg"),             # ARRACACHA *KL y FRESA *KL en PRINCIPAL
    (11.95, True, "12,0 kg"),             # SABILA *KL
    (2.5, False, "3 unidades"),
    (0.5, False, "1 unidad"),
    (10.5, False, "11 unidades"),         # promedio de VINO REGINA PORT en rotación baja
])
def test_empates_como_en_la_app(valor, por_kilo, esperado):
    assert texto_cantidad(valor, por_kilo) == esperado


def test_dias_con_coma_decimal():
    assert [texto_dias(0), texto_dias(5.3), texto_dias(3.0), texto_dias(5.25)] == ["0,0 d", "5,3 d", "3,0 d", "5,3 d"]
