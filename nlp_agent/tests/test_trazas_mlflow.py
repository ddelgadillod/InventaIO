"""Trazas de cada pregunta en MLflow (INV-33, decisión M2): el plan de spans sin MLflow, y contra un MLflow
real con la marca `mlflow`."""
from pathlib import Path

import pytest

from evaluacion import registro_mlflow as rm
from evaluacion import trazas_mlflow as tm

RESULTADOS = Path(rm.__file__).resolve().parent / "resultados"
DECISIONES = RESULTADOS / "2026-10-21_local-decisiones"


def test_plan_de_traza_por_rondas():
    corrida = {"id": "v1-29", "rondas": 2, "ms_total": 1000.0, "ms_modelo": 600.0, "texto": "Las ventas…",
               "llamadas": [{"ronda": 1, "herramienta": "historial_ventas", "argumentos": {"sucursal": "PRINCIPAL"}},
                            {"ronda": 1, "herramienta": "historial_ventas", "argumentos": {"sucursal": "GLORIETA"}}]}
    plan = tm.plan_de_traza(corrida, [{"valor": "$ 1.000", "total": 3}, {"total": 4}], 0)
    assert [(s["nombre"], s["tipo"]) for s in plan["spans"]] == [
        ("modelo · ronda 1", "LLM"), ("historial_ventas", "TOOL"), ("historial_ventas", "TOOL"), ("modelo · ronda 2", "LLM")]
    assert plan["spans"][1]["salida"] == {"valor": "$ [omitido]", "total": 3}          # sin pesos
    assert plan["spans"][-1]["fin"] == plan["fin"] == 1_000_000_000                     # 1 s en ns
    assert all(a["fin"] <= b["inicio"] for a, b in zip(plan["spans"], plan["spans"][1:]))


def test_sin_resultado_se_dice():
    corrida = {"rondas": 1, "ms_total": 10, "ms_modelo": 5, "llamadas": [{"ronda": 1, "herramienta": "x", "argumentos": {}}]}
    assert tm.plan_de_traza(corrida, None, 0)["spans"][1]["sin_resultado"]


def test_el_sintetico_se_recalcula_solo_con_el_mismo_conjunto():
    from evaluacion.conjunto import cargar, herramientas
    meta = {"conjunto": "v1 (local, 61 preguntas)", "huella_conjunto": tm._huella(cargar("local", "v1").model_dump()),
            "huella_catalogo": tm._huella(herramientas("local", "v1"))}              # una corrida con el conjunto de hoy
    assert tm._ejecutor_sintetico(meta)("v1-01") is not None
    assert tm._ejecutor_sintetico({**meta, "huella_conjunto": "otra"}) is None


@pytest.mark.mlflow
def test_con_mlflow_real(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    monkeypatch.chdir(tmp_path)                              # los artefactos de MLflow, fuera del repositorio
    import mlflow
    archivo = tmp_path / "real.jsonl"
    archivo.write_text("\n".join((DECISIONES / "qwen3_8b_gpu_real.jsonl").read_text(encoding="utf-8").splitlines()[:3]) + "\n",
                       encoding="utf-8")
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    [run_id] = rm.registrar([archivo], rm.ClienteMlflow(uri), historia="INV-33")
    assert tm.armar(archivo, run_id, uri, "INV-33") == 2
    assert tm.armar(archivo, run_id, uri, "INV-33") == 0                                  # idempotente
    c = mlflow.MlflowClient(uri)
    trazas = c.search_traces(experiment_ids=[c.get_run(run_id).info.experiment_id], run_id=run_id)
    assert {t.info.tags["pregunta"] for t in trazas} == {"v1-01", "v1-02"}
    t = next(t for t in trazas if t.info.tags["pregunta"] == "v1-01")
    assert [s.span_type for s in t.data.spans] == ["AGENT", "LLM", "TOOL", "LLM"]
    nombres = {a.name for a in t.info.assessments}
    assert {"acierto", "herramienta", "fidelidad", "herramientas_esperadas"} <= nombres
