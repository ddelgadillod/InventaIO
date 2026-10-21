"""Registro en MLflow de las corridas del arnés (INV-31): con un cliente simulado en el CI y con MLflow real
(marca `mlflow`) en local."""
import json
from pathlib import Path

import pytest

from evaluacion import registro_mlflow as rm
from evaluacion.correr import _huella

RESULTADOS = Path(rm.__file__).resolve().parent / "resultados"
V1_REAL = RESULTADOS / "2026-10-21_local" / "qwen3_8b_gpu_real.jsonl"
V0_SPIKE = RESULTADOS / "2026-10-17_local" / "qwen3_8b_gpu.jsonl"


class ClienteFalso:
    def __init__(self):
        self.runs, self.subidos, self.prompts, self.terminados = {}, [], [], []

    def experimento(self, nombre):
        return nombre

    def ya_registrado(self, experimento_id, huella):
        return next((i for i, r in self.runs.items() if r["exp"] == experimento_id and r["tags"]["archivo_sha256"] == huella), None)

    def crear_run(self, experimento_id, nombre, inicio_ms, params, metricas, tags):
        run_id = f"run{len(self.runs)}"
        self.runs[run_id] = {"exp": experimento_id, "nombre": nombre, "inicio": inicio_ms, "params": params,
                             "metricas": metricas, "tags": tags}
        return run_id

    def subir(self, run_id, ruta):
        self.subidos.append((run_id, Path(ruta).name, Path(ruta).read_text(encoding="utf-8")))

    def prompt(self, nombre, texto, run_id):
        self.prompts.append((run_id, nombre))
        return f"{nombre}/1"

    def terminar(self, run_id):
        self.terminados.append(run_id)


def test_un_run_por_archivo_con_parametros_metricas_y_artefactos():
    c = ClienteFalso()
    [run_id] = rm.registrar([V1_REAL], c, historia="INV-31")
    run = c.runs[run_id]
    assert run["exp"] == "agente-conjunto-v1" and run["tags"]["historia"] == "INV-31" and run["tags"]["datos"] == "real"
    assert run["params"]["modelo"] == "qwen3:8b" and run["params"]["digest"] == "500a1f067a9f" and run["params"]["preguntas"] == "49"
    assert 0.6 < run["metricas"]["acierto"] < 0.7 and run["metricas"]["fugas"] == 0
    assert {"acierto_bloque_A", "acierto_bloque_F", "acierto_tipo_abstencion"} <= set(run["metricas"])
    assert run["metricas"]["acierto_bloque_F"] == 1.0 and run["inicio"]
    assert [n for _, n, _ in c.subidos] == ["qwen3_8b_gpu_real.jsonl", "reporte.md", "por_pregunta.csv"]
    assert c.subidos[2][2].startswith("id,corrida,tipo,herramientas,acierto") and c.terminados == [run_id]
    assert c.prompts == [(run_id, "agente-prompt-sistema")]             # la huella del run es la del prompt v1 actual


def test_idempotente():
    c = ClienteFalso()
    primero = rm.registrar([V1_REAL], c)
    assert rm.registrar([V1_REAL], c) == primero and len(c.runs) == 1


def test_v0_viejo_sin_bloques_ni_prompt_actual():
    c = ClienteFalso()
    [run_id] = rm.registrar([V0_SPIKE], c, historia="INV-30")
    run = c.runs[run_id]
    assert run["exp"] == "agente-conjunto-v0" and not any(k.startswith("acierto_bloque") for k in run["metricas"])
    assert run["params"]["datos"] == "sintetico"


def test_prompt_por_huella():
    texto = rm.PROMPTS["agente-prompt-spike"].read_text(encoding="utf-8")
    assert rm._prompt_del_run(_huella(texto)) == ("agente-prompt-spike", texto)
    assert rm._prompt_del_run("000000000000") is None and rm._prompt_del_run(None) is None


def test_solo_servidor_local():
    with pytest.raises(SystemExit, match="local"):
        rm.main([str(V1_REAL), "--tracking-uri", "https://mlflow.ejemplo.com"])


@pytest.mark.mlflow
def test_con_mlflow_real(tmp_path, monkeypatch):
    """Contra un MLflow en SQLite temporal: el run, sus artefactos y el prompt ligado."""
    pytest.importorskip("mlflow")
    monkeypatch.chdir(tmp_path)                    # sin servidor, los artefactos van a ./mlruns
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    cliente = rm.ClienteMlflow(uri)
    [run_id] = rm.registrar([V1_REAL], cliente, historia="INV-31")
    assert rm.registrar([V1_REAL], cliente) == [run_id]
    import mlflow
    run = mlflow.MlflowClient(uri).get_run(run_id)
    assert run.data.tags["prompt"] == "agente-prompt-sistema/1" and run.data.params["datos"] == "real"
    assert {a.path for a in mlflow.MlflowClient(uri).list_artifacts(run_id)} == \
        {"qwen3_8b_gpu_real.jsonl", "reporte.md", "por_pregunta.csv"}
    assert json.loads(Path(mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="qwen3_8b_gpu_real.jsonl",
                                                                 dst_path=str(tmp_path))).read_text().splitlines()[0])["meta"]


def test_correr_con_mlflow_registra_al_terminar(tmp_path, ollama, monkeypatch):
    import httpx

    from evaluacion import correr as correr_mod
    falso = ClienteFalso()
    monkeypatch.setattr(rm, "ClienteMlflow", lambda uri: falso)
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--conjunto", "v1", "--preguntas", "v1-46", "--corridas", "1",
                              "--mlflow", "--historia", "INV-33", "--base-url", "http://ollama-falso:11434",
                              "--salida", str(tmp_path)], transport=httpx.MockTransport(ollama))
    [run] = falso.runs.values()
    assert run["tags"]["historia"] == "INV-33" and run["tags"]["archivo"].endswith(salida.name)
