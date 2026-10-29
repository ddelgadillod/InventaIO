"""INV-20 — Paridad servicio vs. entrenamiento: las features que el servicio
calcula desde la bodega (Postgres) deben ser las mismas de
data/processed_real/matriz_as_of.parquet, la matriz con la que se entrenaron
los modelos, y producir las mismas predicciones.

Necesita la bodega cargada y la matriz de entrenamiento (se genera con los
notebooks 01-07); se salta si falta cualquiera de las dos. Las features
estáticas se calculan a train_end y las dinámicas a fecha_origen, como en 07.
"""
import hashlib

import numpy as np
import pandas as pd
import pytest

from prediccion.features import determinar_rama, features_par, fila_para_motor
from prediccion.motor import predecir
from tests.conftest import MATRIZ_AS_OF

pytestmark = pytest.mark.bodega

N_PARES = 80
TOLERANCIA = 1e-5   # 07 guardó la rejilla en float32


@pytest.fixture(scope="module")
def matriz(modelo_loader):
    if not MATRIZ_AS_OF.is_file():
        pytest.skip(f"Falta {MATRIZ_AS_OF} (se genera con notebooks/07_matriz_as_of.ipynb)")
    huella = hashlib.sha256(MATRIZ_AS_OF.read_bytes()).hexdigest()[:12]
    esperada = modelo_loader.parametros_features["origen"]["matriz_entrenamiento"]
    if huella != esperada:
        pytest.skip(f"matriz_as_of.parquet ({huella}) no es la de entrenamiento de los modelos ({esperada})")
    return pd.read_parquet(MATRIZ_AS_OF)


def test_features_y_predicciones_iguales_a_la_matriz(matriz, bodega_real, modelo_loader):
    parametros = modelo_loader.parametros_features
    calendario = bodega_real.calendario()
    pares = matriz[["codigo_item", "sucursal"]].drop_duplicates().sample(N_PARES, random_state=0)
    pares = pd.concat([pares, pd.DataFrame({"codigo_item": ["P1632", "P1632"], "sucursal": ["PRINCIPAL", "GLORIETA"]})])
    filas = matriz.merge(pares.drop_duplicates(), on=["codigo_item", "sucursal"])

    peor = {f: 0.0 for f in parametros["features"]}
    for (codigo, sucursal), grupo in filas.groupby(["codigo_item", "sucursal"]):
        producto = bodega_real.producto(codigo_item=codigo)
        unidades = bodega_real.ventas_diarias(codigo, sucursal, hasta=grupo["fecha_origen"].max())
        for fila in grupo.itertuples():
            f = features_par(unidades, calendario, fila.fecha_origen, fila.train_end, parametros, producto)
            for k in parametros["features"]:
                v, e = f[k], getattr(fila, k)
                if not (np.isnan(v) and np.isnan(e)):
                    peor[k] = max(peor[k], abs(v - e) / max(1.0, abs(e)))
            assert f["familia_modelo"] == fila.familia_modelo, (codigo, sucursal, fila.fecha_origen)

            fila_servicio = fila_para_motor(f, codigo, sucursal)
            fila_matriz = grupo.loc[[fila.Index]]   # índice de `filas` (el merge lo reinicia), no de `matriz`
            rama = determinar_rama(fila_servicio.iloc[0])
            assert rama == determinar_rama(fila_matriz.iloc[0])
            np.testing.assert_allclose(predecir(modelo_loader.get(rama), fila_servicio),
                                       predecir(modelo_loader.get(rama), fila_matriz), rtol=TOLERANCIA)

    fuera = {k: v for k, v in peor.items() if v > TOLERANCIA}
    assert not fuera, f"features que no coinciden con la matriz de entrenamiento: {fuera}"
