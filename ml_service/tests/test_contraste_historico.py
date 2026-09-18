"""
INV-20 — Contrasta la predicción del modelo REAL contra
target_demanda_15d (el valor histórico que de verdad ocurrió), sobre la
muestra diversa de tests/fixtures/casos_prueba.parquet. Son cotas de
sanidad, no una aserción de exactitud -- el WAPE ya documentado en
INV-17 (0.150-0.416 según la rama) dice cuánto error es esperable.
"""
import numpy as np
import pytest

from prediccion.motor import predecir

RAMAS = ("intermitente", "suave_no_perecedero", "suave_perecedero")


@pytest.mark.parametrize("rama", RAMAS)
def test_predicciones_no_negativas_por_rama(modelo_loader, casos_prueba, rama):
    casos_rama = casos_prueba.loc[casos_prueba["rama"] == rama]
    if casos_rama.empty:
        pytest.skip(f"casos_prueba.parquet no tiene filas de la rama {rama}")
    paquete = modelo_loader.get(rama)
    for idx in casos_rama.index:
        p50, pneg = predecir(paquete, casos_rama.loc[[idx]])
        assert p50 >= 0
        assert pneg >= 0


@pytest.mark.parametrize("rama", RAMAS)
def test_prediccion_en_orden_de_magnitud_del_historico(modelo_loader, casos_prueba, rama):
    """No es una aserción de precisión -- solo que el modelo no esté
    groseramente desviado (ej. prediciendo 1000x el valor real) en la
    mayoría de los casos de esta rama."""
    casos_rama = casos_prueba.loc[casos_prueba["rama"] == rama]
    if casos_rama.empty:
        pytest.skip(f"casos_prueba.parquet no tiene filas de la rama {rama}")
    paquete = modelo_loader.get(rama)
    razones = []
    for idx in casos_rama.index:
        p50, _ = predecir(paquete, casos_rama.loc[[idx]])
        actual = casos_rama.loc[idx, "target_demanda_15d"]
        if actual > 0:
            razones.append(p50 / actual)
    if not razones:
        pytest.skip(f"ningún caso de {rama} tiene target_demanda_15d > 0 para comparar")
    razones = np.array(razones)
    mediana = np.median(razones)
    assert 0.2 <= mediana <= 5.0, (
        f"mediana de pred/actual={mediana:.2f} fuera del rango esperado para {rama} "
        "(el modelo estaría groseramente desviado del histórico, más allá del WAPE documentado)"
    )
