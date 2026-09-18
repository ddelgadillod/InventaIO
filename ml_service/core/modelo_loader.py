"""
InventAI/o — ML Service: carga de modelos
INV-20: carga los 3 modelos campeones de Nivel 1 (INV-17) desde archivos
.joblib LOCALES, ya versionados en el repo (models/) -- NO se descargan
de MLflow en runtime. Decisión explícita del usuario al planear esta HU:
el .joblib ya está disponible, así que agregar una dependencia de red al
servidor MLflow compartido (http://172.16.0.147:5000) en cada arranque
del servicio es innecesario y frágil -- MLflow sigue siendo la fuente de
trazabilidad del entrenamiento (nivel1_metadata.json), no el mecanismo
de serving. Ver docs/INV-20-ml-service.md.
"""
import json
from pathlib import Path
from typing import Optional

import joblib

RAMAS = ("intermitente", "suave_no_perecedero", "suave_perecedero")


class ModeloLoader:
    def __init__(self, modelos_dir: Path):
        self.modelos_dir = Path(modelos_dir)
        self._paquetes: dict = {}
        self.fecha_entrenamiento: Optional[str] = None

    def cargar_todos(self) -> dict:
        for rama in RAMAS:
            path = self.modelos_dir / f"nivel1_{rama}.joblib"
            if not path.is_file():
                raise FileNotFoundError(
                    f"Falta el modelo de la rama '{rama}': {path} -- "
                    "¿corriste notebooks/exportar_modelos_nivel1.py (INV-17)?"
                )
            self._paquetes[rama] = joblib.load(path)

        metadata_path = self.modelos_dir / "nivel1_metadata.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text())
            self.fecha_entrenamiento = metadata.get("fecha_generacion")

        return self._paquetes

    def get(self, rama: str) -> dict:
        if rama not in self._paquetes:
            raise KeyError(f"Rama desconocida o no cargada: {rama}")
        return self._paquetes[rama]

    @property
    def ramas_cargadas(self) -> list:
        return sorted(self._paquetes.keys())
