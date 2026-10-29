"""INV-20 — generar_interpretacion(): reglas fijas, sin I/O."""
from prediccion.interpretacion import generar_interpretacion


def test_rama_suave_no_perecedero_cuantil_alto_recomienda_cobertura():
    texto = generar_interpretacion(
        rama="suave_no_perecedero", prediccion_q50=75.33, limite_superior=98.6,
        alpha_negocio=0.893, horizonte=15,
    )
    assert "Demanda estable" in texto
    assert "perecedero" not in texto
    assert "75 unidades" in texto
    assert "Cobertura recomendada: hasta 99 unidades" in texto


def test_rama_suave_perecedero_cuantil_bajo_advierte_sin_margen():
    texto = generar_interpretacion(
        rama="suave_perecedero", prediccion_q50=14.99, limite_superior=14.96,
        alpha_negocio=0.167, horizonte=15,
    )
    assert "producto perecedero" in texto
    assert "15 unidades" in texto
    assert "No usar como cota de reposición" in texto
    assert "Cobertura recomendada" not in texto


def test_rama_intermitente_cuantil_alto_recomienda_cobertura():
    texto = generar_interpretacion(
        rama="intermitente", prediccion_q50=1.97, limite_superior=4.42,
        alpha_negocio=0.893, horizonte=15,
    )
    assert "Demanda intermitente" in texto
    assert "2 unidades" in texto
    assert "Cobertura recomendada: hasta 4 unidades" in texto


def test_horizonte_se_refleja_en_el_texto():
    texto = generar_interpretacion(
        rama="intermitente", prediccion_q50=1.0, limite_superior=2.0,
        alpha_negocio=0.893, horizonte=15,
    )
    assert "15 días hábiles" in texto


# INV-26 fix (A12): unidad de venta y formato de la app (los mismos casos que
# formato.test.js y api/tests/test_textos_alertas.py)

def test_producto_por_kilo_en_kg_sin_redondear_a_cero():
    # CALABAZIN *KILO en PRINCIPAL: q50 de 0,01 kg salía "0 unidades"
    texto = generar_interpretacion(
        rama="suave_perecedero", prediccion_q50=0.01, limite_superior=0.02,
        alpha_negocio=0.167, horizonte=15, se_vende_por_kilo=True,
    )
    assert "Proyección: 0,01 kg en 15 días hábiles." in texto
    assert "unidades" not in texto


def test_miles_singular_y_empates_como_en_la_app():
    texto = generar_interpretacion(
        rama="intermitente", prediccion_q50=3366.4, limite_superior=4608.5,
        alpha_negocio=0.893, horizonte=15,
    )
    assert "Proyección: 3.366 unidades" in texto
    assert "Cobertura recomendada: hasta 4.609 unidades." in texto
    uno = generar_interpretacion(rama="intermitente", prediccion_q50=0.5, limite_superior=2.05,
                                 alpha_negocio=0.893, horizonte=15)
    assert "Proyección: 1 unidad en" in uno and "hasta 2 unidades." in uno
    kilo = generar_interpretacion(rama="suave_no_perecedero", prediccion_q50=2.05, limite_superior=11.95,
                                  alpha_negocio=0.893, horizonte=15, se_vende_por_kilo=True)
    assert "Proyección: 2,1 kg" in kilo and "hasta 12,0 kg." in kilo
