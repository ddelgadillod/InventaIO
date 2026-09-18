"""
InventAI/o — ML Service: fuente de features
INV-20: lee el extracto local de matriz_as_of.parquet (INV-15) generado
por scripts/generar_datos_locales.py -- NO consulta Postgres en vivo
(nunca se confirmó que cargar_postgres.py se haya corrido con el dato
real en este repo, ver docs/INV-20-ml-service.md). producto_id/sucursal_id
son el código de negocio (codigo_item) y el nombre de sucursal, las
mismas claves que usa todo el pipeline de modelado -- no el SERIAL de
Postgres.
"""
from pathlib import Path
from typing import Optional

import pandas as pd


class FeatureStore:
    def __init__(self, snapshot_path: Path):
        self.snapshot_path = Path(snapshot_path)
        if not self.snapshot_path.is_file():
            raise FileNotFoundError(
                f"Falta {self.snapshot_path} -- correr "
                "scripts/generar_datos_locales.py primero."
            )
        df = pd.read_parquet(self.snapshot_path)
        self._df = df.set_index(["codigo_item", "sucursal"], drop=False)

    def buscar(self, producto_id: str, sucursal_id: str) -> Optional[pd.DataFrame]:
        """Devuelve un DataFrame de 1 fila con las features del par, o
        None si el par no está en el snapshot (sin historia suficiente
        o inexistente -- mismo criterio de cold-start que 07)."""
        clave = (producto_id, sucursal_id)
        if clave not in self._df.index:
            return None
        return self._df.loc[[clave]].iloc[[0]]


def determinar_rama(fila) -> str:
    """Misma taxonomía de 07/08: familia_modelo (suave/intermitente) +
    cond2_perecedero decide entre las 3 ramas del modelo."""
    if fila["familia_modelo"] == "intermitente":
        return "intermitente"
    return "suave_perecedero" if int(fila["cond2_perecedero"]) == 1 else "suave_no_perecedero"
