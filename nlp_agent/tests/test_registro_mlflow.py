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
V0_COLAB_L4 = RESULTADOS / "2026-10-19_colab-l4" / "qwen3_8b_gpu.jsonl"


class ClienteFalso:
    def __init__(self):
        self.runs, self.subidos, self.prompts, self.terminados, self.datasets, self.descripciones = {}, [], [], [], [], {}

    def experimento(self, nombre, descripcion=None):
        self.descripciones[nombre] = descripcion
        return nombre

    def completar(self, run_id, metricas, tags):
        self.runs[run_id]["metricas"] |= metricas
        self.runs[run_id]["tags"] |= tags

    def dataset(self, run_id, nombre, huella, url):
        self.datasets.append((run_id, nombre, huella, url))

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

    def terminar(self, run_id, fin_ms):
        self.terminados.append(run_id)
        self.runs[run_id]["fin"] = fin_ms


def test_un_run_por_archivo_con_parametros_metricas_y_artefactos():
    c = ClienteFalso()
    [run_id] = rm.registrar([V1_REAL], c, historia="INV-31")
    run = c.runs[run_id]
    assert run["exp"] == "agente-conjunto-v1" and run["tags"]["historia"] == "INV-31" and run["tags"]["datos"] == "real"
    assert run["params"]["modelo"] == "qwen3:8b" and run["params"]["digest"] == "500a1f067a9f" and run["params"]["preguntas"] == "49"
    assert 0.6 < run["metricas"]["acierto"] < 0.7 and run["metricas"]["fugas"] == 0
    assert {"acierto_bloque_A", "acierto_bloque_F", "acierto_tipo_abstencion"} <= set(run["metricas"])
    assert run["metricas"]["acierto_bloque_F"] == 1.0 and run["inicio"]
    assert 10 * 60_000 < run["fin"] - run["inicio"] < 3 * 3600_000          # minutos de corrida, no días
    assert [n for _, n, _ in c.subidos] == ["qwen3_8b_gpu_real.jsonl", "reporte.md", "por_pregunta.csv", "fallas.md"]
    assert "## v1-13 · bloque A · falla: herramienta" in c.subidos[3][2] and "**Pregunta:**" in c.subidos[3][2]
    nota = run["tags"]["mlflow.note.content"]
    assert "| Herramienta | 82 % | ≥ 85 % | **no** |" in nota and "Es la línea base" in nota and "B varios pasos 0 %" in nota
    assert run["tags"]["linea_base"] == "sí" and not any(k.startswith("base_") for k in run["metricas"])
    assert run["metricas"]["cumple_meta_herramienta"] == 0.0 and run["metricas"]["cumple_meta_p95"] == 1.0
    assert 0 < run["metricas"]["tasa_hechos"] < 1 and run["tags"]["familia"] == "qwen3"
    [(_, nombre, huella, url)] = c.datasets
    assert nombre == "conjunto-v1-real" and len(huella) == 12 and url.endswith("conjuntos/v1/preguntas.json")
    assert "Conjunto v1 (INV-31)" in c.descripciones["agente-conjunto-v1"]
    assert c.subidos[2][2].startswith("id,corrida,tipo,herramientas,acierto") and c.terminados == [run_id]
    assert c.prompts == [(run_id, "agente-prompt-sistema")]             # la huella del run es la del prompt v1 actual


def test_idempotente_y_actualizar():
    c = ClienteFalso()
    primero = rm.registrar([V1_REAL], c)
    assert rm.registrar([V1_REAL], c) == primero and len(c.runs) == 1
    c.runs[primero[0]]["metricas"].pop("tasa_hechos")
    assert rm.registrar([V1_REAL], c, actualizar=True) == primero and len(c.runs) == 1
    assert "tasa_hechos" in c.runs[primero[0]]["metricas"]


def test_comparacion_con_la_linea_base():
    """Colab L4 del 19-oct frente a la variante colab en el equipo: la diferencia pareada que dio el informe de INV-30."""
    c = ClienteFalso()
    [run_id] = rm.registrar([V0_COLAB_L4], c, historia="INV-30")
    m, tags = c.runs[run_id]["metricas"], c.runs[run_id]["tags"]
    assert tags["comparado_con"] == "2026-10-18_local-variante-colab/qwen3_8b_gpu.jsonl"
    assert round(m["base_dif_acierto"], 3) == 0.023 and m["base_se_separa"] == 0.0 and m["base_preguntas_pareadas"] == 43
    assert "no se separa" in tags["mlflow.note.content"]


def test_v0_viejo_sin_bloques_ni_prompt_actual():
    c = ClienteFalso()
    [run_id] = rm.registrar([V0_SPIKE], c, historia="INV-30")
    run = c.runs[run_id]
    assert run["exp"] == "agente-conjunto-v0" and not any(k.startswith("acierto_bloque") for k in run["metricas"])
    assert run["params"]["datos"] == "sintetico" and run["tags"]["linea_base"] == "sí"


def test_advertencias_de_corridas_no_comparables():
    viejo = RESULTADOS / "2026-10-18_colab-l4" / "llama3.1_8b_gpu.jsonl"
    run = rm.run_de_archivo(viejo)
    assert "Ollama 0.4" in run["tags"]["advertencia"] and "**Advertencias:**" in run["tags"]["mlflow.note.content"]
    real_v0 = rm.run_de_archivo(RESULTADOS / "2026-10-18_local" / "qwen3_8b_gpu_real.jsonl")
    assert "no se califican" in real_v0["tags"]["advertencia"]


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
    experimento = mlflow.MlflowClient(uri).get_experiment(run.info.experiment_id)
    assert experimento.tags["mlflow.experimentKind"] == "custom_model_development"
    assert {a.path for a in mlflow.MlflowClient(uri).list_artifacts(run_id)} == \
        {"qwen3_8b_gpu_real.jsonl", "reporte.md", "por_pregunta.csv", "fallas.md"}
    assert [d.dataset.name for d in run.inputs.dataset_inputs] == ["conjunto-v1-real"]
    assert "Herramienta" in run.data.tags["mlflow.note.content"]
    assert rm.registrar([V1_REAL], cliente, actualizar=True) == [run_id]          # sin duplicar el dataset
    assert len(mlflow.MlflowClient(uri).get_run(run_id).inputs.dataset_inputs) == 1
    assert json.loads(Path(mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="qwen3_8b_gpu_real.jsonl",
                                                                 dst_path=str(tmp_path))).read_text().splitlines()[0])["meta"]


def test_correr_con_mlflow_registra_al_terminar(tmp_path, ollama, monkeypatch):
    import httpx

    from evaluacion import correr as correr_mod
    falso = ClienteFalso()
    monkeypatch.setattr(rm, "ClienteMlflow", lambda uri: falso)
    from evaluacion import documentar_mlflow as dm
    documentado = []

    class DocumentadorFalso:
        def __init__(self, uri):
            pass

        def prompts(self):
            documentado.append("prompts")

        def datasets(self):
            documentado.append("datasets")

        def versiones(self):
            documentado.append("versiones")
    monkeypatch.setattr(dm, "Documentador", DocumentadorFalso)
    from evaluacion import trazas_mlflow
    trazas = []
    monkeypatch.setattr(trazas_mlflow, "armar", lambda ruta, run_id, uri, historia: trazas.append((run_id, historia)) or 1)
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--conjunto", "v1", "--preguntas", "v1-46", "--corridas", "1",
                              "--mlflow", "--historia", "INV-33", "--base-url", "http://ollama-falso:11434",
                              "--salida", str(tmp_path)], transport=httpx.MockTransport(ollama))
    [run] = falso.runs.values()
    assert run["tags"]["historia"] == "INV-33" and run["tags"]["archivo"].endswith(salida.name)
    assert documentado == ["prompts", "datasets", "versiones"]
    [run_id] = falso.runs
    assert trazas == [(run_id, "INV-33")]                                    # M2: las trazas, ligadas al run
    assert run["tags"]["tipo"] == "sonda" and "sonda" in run["nombre"]       # M3: con --preguntas, una sonda
    assert len(run["tags"]["mlflow.source.git.commit"]) == 40                # M4: de qué código sale


def test_tipo_de_las_corridas_viejas():
    assert rm.tipo_de({}, 61) == "completa" and rm.tipo_de({}, 7) == "sonda"
    assert rm.tipo_de({"tipo": "smoke"}, 5) == "smoke"

