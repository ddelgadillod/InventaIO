"""Recalificación con el verificador del agente (INV-33, Z12): el calificador y el verificador miden lo mismo."""
from pathlib import Path

import pytest

from evaluacion import recalificar_mlflow as rq

DECISIONES = Path(rq.__file__).resolve().parent / "resultados" / "2026-10-21_local-decisiones"


def _primeras(tmp_path, nombre, n=12):
    destino = tmp_path / nombre
    destino.write_text("\n".join((DECISIONES / nombre).read_text(encoding="utf-8").splitlines()[: n + 1]) + "\n",
                       encoding="utf-8")
    return destino


@pytest.mark.parametrize("nombre", ["qwen3_8b_gpu.jsonl", "qwen3_8b_gpu_real.jsonl"])
def test_el_verificador_coincide_con_lo_guardado(tmp_path, nombre):
    _, filas = rq.filas(_primeras(tmp_path, nombre))
    m = rq.metricas(filas)
    assert m["respuestas"] == 12 and m["cambian_fidelidad"] == 0
    assert 0 <= m["tasa_fecha_omitida"] <= 1 and m["con_datos"] <= 12


@pytest.mark.mlflow
def test_con_mlflow_real(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    import mlflow
    monkeypatch.chdir(tmp_path)
    archivo = _primeras(tmp_path, "qwen3_8b_gpu_real.jsonl", 4)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    run_id = rq.registrar(archivo, uri, "INV-33")
    assert rq.registrar(archivo, uri, "INV-33") == run_id                      # no se repite con el mismo verificador
    run = mlflow.MlflowClient(uri).get_run(run_id)
    assert run.data.tags["tipo"] == "recalificacion" and run.data.metrics["respuestas"] == 4
