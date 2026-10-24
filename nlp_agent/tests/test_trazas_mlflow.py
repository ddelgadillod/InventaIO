"""Trazas de cada pregunta en MLflow (INV-33, decisión M2): el plan de spans sin MLflow, y contra un MLflow
real con la marca `mlflow`."""
import json
from pathlib import Path

import pytest

from evaluacion import registro_mlflow as rm
from evaluacion import trazas_mlflow as tm
from tests.mlflow_falso import instalar

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


# --- Con el MLflow simulado (corren en el CI; M2 de INV-31) ---

def test_armar_con_mlflow_simulado_real_e_idempotente(tmp_path, monkeypatch):
    falso = instalar(monkeypatch)
    archivo = tmp_path / "real.jsonl"
    archivo.write_text("\n".join((DECISIONES / "qwen3_8b_gpu_real.jsonl").read_text(encoding="utf-8").splitlines()[:3]) + "\n",
                       encoding="utf-8")
    run = falso.create_run("exp0").info.run_id
    assert tm.armar(archivo, run, "sqlite:///simulado.db", "INV-33") == 2
    assert tm.armar(archivo, run, "sqlite:///simulado.db", "INV-33") == 0                  # idempotente
    assert falso.uri == "sqlite:///simulado.db"
    traza = next(t for t in falso.trazas.values() if t["tags"]["pregunta"] == "v1-01")
    assert traza["run"] == run and traza["tags"]["historia"] == "INV-33" and traza["tags"]["datos"] == "real"
    assert traza["spans"][0] == "AGENT" and {"LLM", "TOOL"} <= set(traza["spans"]) and traza["estado"] == "OK"
    nombres = {(tipo, nombre) for _, tipo, nombre, _ in falso.evaluaciones}
    assert {("feedback", "acierto"), ("feedback", "fidelidad"), ("expectativa", "herramientas_esperadas")} <= nombres


def test_armar_recalcula_los_resultados_sinteticos(tmp_path, monkeypatch):
    from evaluacion.conjunto import cargar, herramientas
    falso = instalar(monkeypatch)
    meta = {"meta": True, "modelo": "qwen3:8b", "conjunto": "v1 (local, 61 preguntas)", "inicio": "2026-10-24T10:00:00",
            "huella_conjunto": tm._huella(cargar("local", "v1").model_dump()), "huella_catalogo": tm._huella(herramientas("local", "v1"))}
    calificacion = {"acierto": False, "fidelidad": False, "cifras_sin_respaldo": ["12"]}
    corridas = [
        {"id": "v1-01", "corrida": 1, "rondas": 2, "ms_total": 900, "ms_modelo": 600, "texto": "…", "calificacion": calificacion,
         "llamadas": [{"ronda": 1, "herramienta": "buscar_producto", "argumentos": {"texto": "Leche Colanta * 1100"}},
                      {"ronda": 1, "herramienta": "no_existe", "argumentos": {}}]},
        {"id": "x-99", "corrida": 1, "rondas": 1, "error": "tiempo_agotado", "calificacion": {"acierto": False}},
    ]
    archivo = tmp_path / "sintetico.jsonl"
    archivo.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [meta, *corridas]) + "\n", encoding="utf-8")
    assert tm.armar(archivo, falso.create_run("exp0").info.run_id, "sqlite:///simulado.db") == 2
    sintetica, desconocida = falso.trazas.values()
    assert sintetica["spans"] == ["AGENT", "LLM", "TOOL", "TOOL", "LLM"] and sintetica["tags"]["datos"] == "local"
    assert desconocida["entradas"]["pregunta"] is None and desconocida["estado"] == "ERROR"
    assert ("tr0", "feedback", "fidelidad", False) in falso.evaluaciones


def test_main_registra_y_arma_solo_en_local(monkeypatch, capsys):
    llamadas = []
    monkeypatch.setattr(rm, "ClienteMlflow", lambda uri: uri)
    monkeypatch.setattr(rm, "registrar", lambda rutas, cliente, historia: [f"run-{rutas[0].name}"])
    monkeypatch.setattr(tm, "armar", lambda ruta, run_id, uri, historia: llamadas.append(run_id) or (2 if "a" in ruta.name else 0))
    assert tm.main(["a.jsonl", "b.jsonl", "--tracking-uri", "sqlite:///x.db"]) == 2
    assert llamadas == ["run-a.jsonl", "run-b.jsonl"] and "las trazas ya estaban" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        tm.main(["a.jsonl", "--tracking-uri", "https://mlflow.externo.example"])
