#!/usr/bin/env python3
"""
INV-20 — Genera los dos extractos locales que usa ml_service, a partir
de matriz_as_of.parquet (INV-15). No se corre en Docker ni en el
servicio -- es un paso manual de preparación (ver docs/INV-20-ml-service.md).

1. data/features_snapshot.parquet -- la fila MÁS RECIENTE (mayor
   fecha_origen) por (codigo_item, sucursal). Es lo que consume el
   endpoint /api/predict en producción: el estado as-of "actual" de
   cada par.
2. tests/fixtures/casos_prueba.parquet -- una muestra DIVERSA (varias
   ramas, varios folds/orígenes), que conserva target_demanda_15d (el
   valor real que ocurrió) -- solo para los tests, que contrastan la
   predicción contra ese histórico (ver tests/test_contraste_historico.py).
   Pedido explícito del usuario al planear esta HU: los datos de prueba
   deben ser diversos y permitir contrastar contra un histórico, no
   reusar directamente el snapshot de producción.
"""
import sys
from pathlib import Path

import pandas as pd

MATRIZ_AS_OF = Path(__file__).resolve().parent.parent.parent / "data" / "processed_real" / "matriz_as_of.parquet"
SNAPSHOT_OUT = Path(__file__).resolve().parent.parent / "data" / "features_snapshot.parquet"
CASOS_PRUEBA_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "casos_prueba.parquet"

N_POR_RAMA_PRUEBA = 15  # filas por rama en el fixture de test
SEMILLA = 42


def _rama_de(fila) -> str:
    if fila["familia_modelo"] == "intermitente":
        return "intermitente"
    return "suave_perecedero" if int(fila["cond2_perecedero"]) == 1 else "suave_no_perecedero"


def generar_snapshot_produccion(matriz: pd.DataFrame) -> pd.DataFrame:
    """Fila más reciente por (codigo_item, sucursal) -- el estado as-of
    'actual' que usa el servicio para predecir."""
    idx_mas_reciente = matriz.groupby(["codigo_item", "sucursal"])["fecha_origen"].idxmax()
    return matriz.loc[idx_mas_reciente].reset_index(drop=True)


def generar_casos_prueba(matriz: pd.DataFrame) -> pd.DataFrame:
    """Muestra diversa -- varias ramas, varios folds -- CON el target
    real, para que los tests puedan contrastar predicción vs. histórico
    (test_contraste_historico.py)."""
    matriz = matriz.copy()
    matriz["rama"] = matriz.apply(_rama_de, axis=1)
    partes = []
    for rama, grupo in matriz.groupby("rama"):
        n_folds = grupo["fold_id"].nunique()
        por_fold = max(1, N_POR_RAMA_PRUEBA // n_folds)
        muestra = (
            grupo.groupby("fold_id", group_keys=False)
            .apply(lambda g: g.sample(min(len(g), por_fold), random_state=SEMILLA))
        )
        if len(muestra) > N_POR_RAMA_PRUEBA:
            muestra = muestra.sample(N_POR_RAMA_PRUEBA, random_state=SEMILLA)
        partes.append(muestra)
    return pd.concat(partes, ignore_index=True)


def main():
    if not MATRIZ_AS_OF.is_file():
        print(f"Falta {MATRIZ_AS_OF} -- correr 07_matriz_as_of.ipynb (INV-15) primero.")
        sys.exit(1)

    matriz = pd.read_parquet(MATRIZ_AS_OF)

    SNAPSHOT_OUT.parent.mkdir(parents=True, exist_ok=True)
    snapshot = generar_snapshot_produccion(matriz)
    snapshot.to_parquet(SNAPSHOT_OUT, index=False)
    print(f"guardado: {SNAPSHOT_OUT} ({len(snapshot):,} filas -- 1 por par producto x sucursal)")

    CASOS_PRUEBA_OUT.parent.mkdir(parents=True, exist_ok=True)
    casos = generar_casos_prueba(matriz)
    casos.to_parquet(CASOS_PRUEBA_OUT, index=False)
    print(f"guardado: {CASOS_PRUEBA_OUT} ({len(casos):,} filas)")
    print(casos["rama"].value_counts().to_string())


if __name__ == "__main__":
    main()
