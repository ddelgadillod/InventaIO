"""Recalificación de las corridas guardadas con el calificador vigente (INV-33, 23-oct): el archivo cambia en su
lugar y su run de MLflow se actualiza, sin crear otro."""
import json
import shutil
from pathlib import Path

from evaluacion import recalificar_calificador as rc
from evaluacion import registro_mlflow as rm
from tests.test_registro_mlflow import ClienteFalso

CONFIRMACION = Path(rm.__file__).resolve().parent / "resultados" / "2026-10-22_local-prompt-v2-1-confirmacion" / "qwen3_8b_gpu_real.jsonl"


def test_actualiza_el_run_sin_crear_otro(tmp_path):
    ruta = tmp_path / "2026-10-22_local-prompt-v2-1-confirmacion" / "qwen3_8b_gpu_real.jsonl"
    ruta.parent.mkdir()
    shutil.copy(CONFIRMACION, ruta)
    c = ClienteFalso()
    [run_id] = rm.registrar([ruta], c)
    antes = c.runs[run_id]["tags"]["archivo_sha256"]
    [fila] = rc.recalificar([ruta], c)
    assert fila["run"] == run_id and len(c.runs) == 1
    tags = c.runs[run_id]["tags"]
    assert tags["archivo_sha256"] != antes and tags["calificador"] == rc.huella_calificador() and tags["recalificado"]
    assert "herramienta_ejecutada" in c.runs[run_id]["metricas"] and "sin_datos_con_contenido" in c.runs[run_id]["metricas"]
    corridas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()[1:]]
    assert all("sin_datos_con_contenido" in x["calificacion"] for x in corridas)


def test_sin_registro_solo_el_archivo(tmp_path):
    ruta = tmp_path / "x.jsonl"
    shutil.copy(CONFIRMACION, ruta)
    [fila] = rc.recalificar([ruta], ClienteFalso())
    assert fila["run"] is None and fila["cambios"] > 0
