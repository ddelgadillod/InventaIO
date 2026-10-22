"""Documentación de las secciones Prompts, Datasets y Agent versions en MLflow (INV-31), con los datos reales
del repositorio: sin MLflow en el CI y contra un MLflow real con la marca `mlflow`."""
import subprocess
from pathlib import Path

import pytest

from evaluacion import documentar_mlflow as dm
from evaluacion import registro_mlflow as rm

RESULTADOS = Path(rm.__file__).resolve().parent / "resultados"
V1_REAL = RESULTADOS / "2026-10-21_local" / "qwen3_8b_gpu_real.jsonl"                      # línea base
# La medición con el catálogo y el glosario actuales (glosario ampliado, 21-oct): sus huellas son las de hoy
V1_ACTUAL = RESULTADOS / "2026-10-21_local-glosario-ampliado" / "qwen3_8b_gpu_real.jsonl"
V0_VARIANTE = RESULTADOS / "2026-10-18_local-variante-colab" / "qwen3_8b_gpu.jsonl"
V0_COLAB_L4 = RESULTADOS / "2026-10-19_colab-l4" / "qwen3_8b_gpu.jsonl"


def test_registros_del_v1_salen_del_conjunto():
    registros = dm.registros("v1")
    assert len(registros) == 61
    assert all(set(r["inputs"]) == {"pregunta", "rol", "sucursal_usuario"} for r in registros)
    por_id = {r["tags"]["id"]: r for r in registros}
    assert por_id["v1-13"]["expectations"]["herramientas_esperadas"] == ["resumen_alertas"]
    assert por_id["v1-13"]["expectations"]["hechos_reales"] == ["1334", "386", "2732"]
    assert por_id["v1-46"]["expectations"]["abstencion"] is True and por_id["v1-46"]["tags"]["bloque"] == "E"
    assert not any("pendiente" in r["tags"] for r in registros)          # INV-33: B1 a B4 ya están


def test_etiquetas_del_conjunto_y_su_huella_es_la_de_las_corridas():
    e = dm.etiquetas_conjunto("v1")
    assert (e["preguntas"], e["activas"], e["pendientes"]) == ("61", "61", "0") and e["fecha_datos"] == "2025-12-31"
    from evaluacion.conjunto import cargar
    from evaluacion.correr import _huella
    assert e["huella"] == _huella(cargar("local", "v1").model_dump())     # la misma huella que guardará la corrida


def test_info_de_los_prompts_desde_el_repositorio():
    info = dm.info_prompt("agente-prompt-sistema")
    assert info["archivo"] == "nlp_agent/prompts/v1/sistema.md"
    assert info["huella"] == rm.run_de_archivo(V1_REAL)["huella_prompt"]


def test_el_catalogo_del_v1_tiene_nombre():
    from herramientas.catalogo import esquemas
    huella = dm._huella(esquemas())                  # el catálogo de hoy: cambia con cada herramienta nueva
    assert dm.catalogos_conocidos()[huella] == f"catálogo del agente ({len(esquemas())} herramientas, {huella[:8]})"
    assert rm.run_de_archivo(V1_REAL)["params"]["huella_catalogo"] not in dm.catalogos_conocidos()   # la línea base usó otro


def test_nombre_de_version_sin_caracteres_prohibidos():
    from herramientas.catalogo import esquemas
    params = {**rm.run_de_archivo(V1_ACTUAL)["params"], "huella_catalogo": dm._huella(esquemas())}
    v = dm.clave_version(params, {"prompt": "agente-prompt-sistema/1"}, dm.catalogos_conocidos())
    assert v["descripcion"].startswith(f"agente · qwen3:8b · agente-prompt-sistema/1 · catálogo del agente ({len(esquemas())} herramientas, ")
    assert not set("/:.%\"'") & set(v["nombre"])


def _commit_disponible(commit: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", commit], cwd=dm.RAIZ, capture_output=True).returncode == 0


@pytest.mark.skipif(not _commit_disponible("ca6333c"), reason="el CI clona sin historia (fetch-depth 1)")
def test_colab_del_19_oct_es_la_misma_version_que_la_variante_en_el_equipo():
    """Sin huellas en su meta, pero con su commit: git dice que el prompt y el catálogo eran los mismos."""
    catalogos = dm.catalogos_conocidos()
    prompts = {dm._huella(rm.PROMPTS["agente-prompt-spike"].read_text(encoding="utf-8")): "agente-prompt-spike/1"}
    colab = dm.clave_version(rm.run_de_archivo(V0_COLAB_L4)["params"], {}, catalogos, prompts)
    equipo = dm.clave_version(rm.run_de_archivo(V0_VARIANTE)["params"], {}, catalogos, prompts)
    assert colab["clave"] == equipo["clave"] and colab["huellas_derivadas_de"] == "ca6333c"
    assert colab["prompt"] == "agente-prompt-spike/1" and colab["catalogo"] == "catálogo del spike (variante colab)"


def test_sin_commit_ni_huellas_no_se_deriva_nada():
    viejo = rm.run_de_archivo(RESULTADOS / "2026-10-18_colab-l4" / "llama3.1_8b_gpu.jsonl")["params"]
    assert dm.huellas_por_commit(viejo) == {}
    assert dm.clave_version(viejo, {}, {})["prompt"] == "prompt sin huella"


def test_solo_servidor_local():
    with pytest.raises(SystemExit, match="local"):
        dm.main(["--tracking-uri", "https://mlflow.ejemplo.com"])


@pytest.mark.mlflow
def test_con_mlflow_real(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    monkeypatch.chdir(tmp_path)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    [run_id] = rm.registrar([V1_REAL], rm.ClienteMlflow(uri), historia="INV-31")
    d = dm.Documentador(uri)
    assert d.prompts() == ["agente-prompt-sistema/1"]
    assert d.datasets() == ["conjunto-v1 (61 registros)"]
    assert d.datasets() == ["conjunto-v1 (sin cambios)"]
    [version] = d.versiones()
    assert version.endswith("← 1 runs")
    d.versiones()                                                    # idempotente: no duplica enlaces ni métricas
    import mlflow
    c = mlflow.MlflowClient(uri)
    [modelo] = c.search_logged_models([c.get_run(run_id).info.experiment_id])
    assert [m.model_id for m in c.get_run(run_id).inputs.model_inputs] == [modelo.model_id]
    assert {m.key for m in modelo.metrics} >= {"acierto", "herramienta"} and len(modelo.metrics) == 6
    assert mlflow.genai.load_prompt("prompts:/agente-prompt-sistema@vigente").version == 1
    # Una recalificación (INV-33, M3) en el mismo experimento no corre el modelo: no es una versión ni rompe el paso
    c.create_run(c.get_run(run_id).info.experiment_id, run_name="recalificación", tags={"tipo": "recalificacion"})
    assert d.versiones() == [version]


def test_la_clave_no_depende_de_los_nombres():
    """Si el catálogo vigente cambia, una versión vieja cambia de nombre legible pero no de identidad."""
    params = rm.run_de_archivo(V1_REAL)["params"]
    con_nombre = dm.clave_version(params, {}, {params["huella_catalogo"]: "catálogo del agente (9 herramientas)"})
    sin_nombre = dm.clave_version(params, {}, {})
    assert con_nombre["clave"] == sin_nombre["clave"] and con_nombre["catalogo"] != sin_nombre["catalogo"]
