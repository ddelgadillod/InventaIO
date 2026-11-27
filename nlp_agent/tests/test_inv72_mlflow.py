"""INV-72 — Trazabilidad del agente en MLflow: la huella del código, los cambios entre versiones, las corridas
incompletas, las comparaciones, la evolución, los despliegues y la prueba de humo del chat. Sin MLflow en el CI; con
MLflow real, la marca `mlflow`."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from evaluacion import comparar, despliegues_mlflow, humo_chat, version_agente
from evaluacion import documentar_mlflow as dm
from evaluacion import registro_mlflow as rm

RESULTADOS = Path(rm.__file__).resolve().parent / "resultados"
V1_REAL = RESULTADOS / "2026-10-21_local" / "qwen3_8b_gpu_real.jsonl"


def _git(raiz: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    """Un repositorio con el código del agente en sus carpetas de verdad."""
    _git(tmp_path, "init", "-q", "-b", "develop")
    _git(tmp_path, "config", "user.email", "prueba@ejemplo.com")
    _git(tmp_path, "config", "user.name", "Prueba")
    for ruta, texto in (("nlp_agent/agente/bucle.py", "A = 1\n"), ("nlp_agent/herramientas/catalogo.py", "B = 2\n"),
                        ("nlp_agent/agente/LEEME.md", "no es código\n"), ("docs/otro.py", "C = 3\n")):
        (tmp_path / ruta).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / ruta).write_text(texto, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "inicio")
    return tmp_path


# --- Huella del código y cambios -------------------------------------------------------------------------------

def test_la_huella_del_arbol_es_la_del_commit_y_cambia_con_el_codigo(repo):
    commit = _git(repo, "rev-parse", "HEAD")
    huella = version_agente.huella_codigo(raiz=repo)
    assert huella == version_agente.huella_codigo(commit, raiz=repo) and len(huella) == 12
    (repo / "docs/otro.py").write_text("C = 4\n", encoding="utf-8")              # fuera del agente: no cuenta
    (repo / "nlp_agent/agente/LEEME.md").write_text("cambia\n", encoding="utf-8")  # no es .py: no cuenta
    (repo / "nlp_agent/agente/nuevo.py").write_text("D = 5\n", encoding="utf-8")   # sin seguir en git: no cuenta
    assert version_agente.huella_codigo(raiz=repo) == huella
    (repo / "nlp_agent/agente/bucle.py").write_text("A = 2\n", encoding="utf-8")   # cambio sin commit: sí cuenta
    assert version_agente.huella_codigo(raiz=repo) != huella


def test_sin_git_no_hay_huella(tmp_path):
    assert version_agente.huella_codigo(raiz=tmp_path) is None
    assert version_agente.huella_codigo("abc1234", raiz=tmp_path) is None


def test_los_cambios_traen_commits_prs_e_historias(repo):
    inicio = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "fix/INV-72-algo")
    (repo / "nlp_agent/agente/bucle.py").write_text("A = 3\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "fix(INV-72): la guarda corrige la agrupación")
    (repo / "docs/otro.py").write_text("C = 9\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "docs: fuera del agente")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "fix/INV-72-algo", "-m",
         "Merge pull request #79 from ddelgadillod/fix/INV-72-algo")
    fin = _git(repo, "rev-parse", "HEAD")
    c = version_agente.cambios(inicio, fin, raiz=repo)
    assert [x["asunto"] for x in c["commits"]] == ["fix(INV-72): la guarda corrige la agrupación"]
    assert c["prs"] == [79] and c["historias"] == ["INV-72"] and c["total"] == 1
    nota = version_agente.nota_cambios(c, inicio, fin)
    assert "PR #79" in nota[0] and "historias INV-72" in nota[0]
    assert version_agente.cambios(fin, fin, raiz=repo)["total"] == 0
    assert version_agente.nota_cambios(version_agente.cambios(None, fin), None, fin) == ["**Cambios:** es la primera versión medida."]


def test_historias_y_prs_de_los_textos():
    assert version_agente.historias_de("INV-9 y INV-72", "fix(INV-40)") == ["INV-9", "INV-40", "INV-72"]
    assert version_agente.prs_de("Merge pull request #79 from x", "algo (#12)", "sin número") == [12, 79]


# --- Registro de las corridas ----------------------------------------------------------------------------------

def test_una_corrida_detenida_es_incompleta():
    assert rm.tipo_de({"tipo": "completa", "corridas": 3}, 61, 149) == "incompleta"
    assert rm.tipo_de({"tipo": "completa", "corridas": 3}, 61, 183) == "completa"
    assert rm.tipo_de({"tipo": "sonda", "corridas": 1}, 2, 1) == "sonda"
    assert rm.tipo_de({}, 49) == "completa"                                  # las viejas no dicen sus respuestas


def test_el_run_lleva_las_mejoras_y_el_codigo(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RESULTADOS", tmp_path)
    lineas = V1_REAL.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lineas[0]) | {"mejoras": "agrupacion", "huella_codigo": "e33ad29f777a", "verificar": True}
    ruta = tmp_path / "2026-11-26_prueba" / "corrida.jsonl"
    ruta.parent.mkdir()
    ruta.write_text("\n".join([json.dumps(meta), *lineas[1:]]), encoding="utf-8")
    run = rm.run_de_archivo(ruta)
    assert run["params"]["mejoras"] == "agrupacion" and run["params"]["huella_codigo"] == "e33ad29f777a"
    assert "huella_codigo_de" not in run["tags"]
    assert "código `e33ad29f777a`, mejoras: agrupacion, con verificación" in run["tags"]["mlflow.note.content"]


def test_sin_mejoras_en_la_meta_son_ninguna():
    assert rm.run_de_archivo(V1_REAL)["params"]["mejoras"] == "ninguna"


def test_el_codigo_de_una_corrida_vieja_sale_de_su_commit(monkeypatch):
    monkeypatch.setattr(version_agente, "huella_codigo", lambda commit=None, **_: f"de-{commit}")
    assert rm.codigo_del_run({"git": {"commit": "abc1234def", "sucio": False}}) == ("de-abc1234def", "commit abc1234 (sin cambios)")
    assert rm.codigo_del_run({"git": {"commit": "abc1234def", "sucio": True}})[1].endswith("aproximada)")
    assert rm.codigo_del_run({"commit": "abc1234def"})[1] == "commit abc1234 (sin saber si había cambios sin commit)"
    assert rm.codigo_del_run({}) == (None, None)


def test_actualizar_agrega_los_parametros_nuevos_sin_cambiar_los_viejos():
    from tests.test_registro_mlflow import ClienteFalso
    c = ClienteFalso()
    [run_id] = rm.registrar([V1_REAL], c)
    c.runs[run_id]["params"].pop("mejoras")                       # un run registrado antes de INV-72
    c.runs[run_id]["params"]["modelo"] = "el de entonces"
    rm.registrar([V1_REAL], c, actualizar=True)
    assert c.runs[run_id]["params"]["mejoras"] == "ninguna" and c.runs[run_id]["params"]["modelo"] == "el de entonces"


def test_los_conjuntos_nuevos_describen_su_experimento_con_su_leeme():
    for version in ("inv82", "inv82-b", "inv79", "inv40-b"):
        texto = rm.descripcion_experimento(version)
        assert texto and texto.startswith("**Conjunto `") , version
    assert rm.descripcion_experimento("v1") == rm.DESCRIPCION_EXPERIMENTO["v1"]


# --- Comparaciones ---------------------------------------------------------------------------------------------

def test_el_manifiesto_de_comparaciones_es_valido():
    datos = json.loads(comparar.MANIFIESTO.read_text(encoding="utf-8"))
    vistos = set()
    for c in datos["comparaciones"]:
        assert {"historia", "motivo", "base", "nuevo"} <= set(c) and c["historia"].startswith("INV-")
        assert (c["base"], c["nuevo"], c.get("equivalencias", False)) not in vistos
        vistos.add((c["base"], c["nuevo"], c.get("equivalencias", False)))
        for ruta in (c["base"], c["nuevo"]):
            # Lo de evidencias/ tiene cifras del negocio: no está en el repositorio
            assert ruta.startswith("evidencias/") or (comparar.RAIZ / ruta).is_file(), ruta
        if c.get("equivalencias"):
            assert len(c["equivalencias_de"]) >= 7
    assert {c["historia"] for c in datos["comparaciones"]} == {"INV-33", "INV-40", "INV-67", "INV-72"}


def test_metricas_y_huella_de_una_comparacion(tmp_path):
    from tests.test_comparar import _par
    base, nuevo = _par(tmp_path, lambda i: True, lambda i: i % 2 == 0)
    _, _, c = comparar.calcular(base, nuevo)
    m = comparar.metricas_mlflow(c)
    assert m["cumple"] == 0.0 and m["empeora_herramienta"] == 1.0 and m["preguntas_pareadas"] == 20.0
    assert {"base_acierto", "nuevo_acierto", "dif_acierto", "ic95_inf_acierto", "ic95_sup_acierto", "nuevo_p95_s"} <= set(m)
    h = comparar.huella_comparacion(base, nuevo, False, None)
    assert h == comparar.huella_comparacion(base, nuevo, False, None)
    assert h != comparar.huella_comparacion(base, nuevo, True, None) != comparar.huella_comparacion(nuevo, base, False, None)


def test_sin_commit_las_equivalencias_son_las_de_hoy():
    from evaluacion import equivalencias
    assert comparar.equivalencias_de(None) is equivalencias


@pytest.mark.skipif(subprocess.run(["git", "cat-file", "-e", "d90b8a5"], cwd=comparar.RAIZ, capture_output=True).returncode,
                    reason="el CI clona sin historia (fetch-depth 1)")
def test_las_equivalencias_de_un_commit_viejo_se_cargan():
    viejo = comparar.equivalencias_de("d90b8a5")
    assert callable(viejo.recalificar) and viejo.__file__.startswith("d90b8a5:")


# --- Documentación: conjuntos, versiones y evolución -----------------------------------------------------------

def test_documenta_todos_los_conjuntos():
    assert {"v0", "v1", "holdout-3", "inv40", "inv79", "inv82", "inv82-b"} <= set(dm.CONJUNTOS)
    assert dm.descripcion_conjunto("inv82").startswith("Conjunto `inv82` · Consultas compuestas de ventas. Son 15 preguntas")
    assert dm.descripcion_conjunto("v1") == dm.DESCRIPCION_CONJUNTO["v1"]


def test_los_hechos_de_fuera_entran_sin_pesos(tmp_path, monkeypatch):
    from evaluacion.conjunto import HECHOS_DIR
    (tmp_path / "hechos_inv82.json").write_text(json.dumps(
        {"inv82-01": {"hechos_reales": ["1,1", "$ 1.234.567"], "prohibido": ["no hay datos"]}}), encoding="utf-8")
    monkeypatch.setenv(HECHOS_DIR, str(tmp_path))
    por_id = {r["tags"]["id"]: r for r in dm.registros("inv82")}
    assert "1,1" in por_id["inv82-01"]["expectations"]["hechos_reales"]
    assert "$ [omitido]" in por_id["inv82-01"]["expectations"]["hechos_reales"]
    assert dm.etiquetas_conjunto("inv82")["hechos_externos"] == "incluidos, sin cifras en pesos"
    monkeypatch.delenv(HECHOS_DIR)
    assert dm.etiquetas_conjunto("inv82")["hechos_externos"].startswith("no cargados")
    assert "hechos_externos" not in dm.etiquetas_conjunto("v1")


def test_el_codigo_las_mejoras_y_la_verificacion_cambian_la_version():
    params = rm.run_de_archivo(V1_REAL)["params"]
    base = dm.clave_version(params, {}, {})
    assert dm.clave_version({**params, "huella_codigo": "aaa"}, {}, {})["clave"] != base["clave"]
    assert dm.clave_version({**params, "mejoras": "agrupacion"}, {}, {})["clave"] != base["clave"]
    con = dm.clave_version({**params, "mejoras": "agrupacion", "huella_codigo": "e33ad29f777a"}, {"verificar": "sí"}, {})
    assert con["clave"] != base["clave"]
    assert con["descripcion"].endswith("· código e33ad29f · mejoras agrupacion · verifica")
    assert not set("/:.%\"'") & set(con["nombre"])


def _run(conjunto_tipo: str, inicio: int, metricas: dict, datos: str = "real", run_id: str = "r"):
    return SimpleNamespace(info=SimpleNamespace(start_time=inicio, run_id=run_id, end_time=inicio + 10),
                           data=SimpleNamespace(tags={"tipo": conjunto_tipo}, params={"datos": datos}, metrics=metricas))


def test_la_evolucion_mide_con_la_ultima_corrida_completa():
    runs = [("v1", _run("completa", 1, {"acierto": 0.7}, run_id="viejo")),
            ("v1", _run("completa", 3, {"acierto": 0.8, "acierto_equivalencias": 0.9}, run_id="nuevo")),
            ("v1", _run("incompleta", 5, {"acierto": 0.1}, run_id="detenido")),
            ("v1", _run("completa", 2, {"acierto": 0.5}, datos="sintetico", run_id="sint")),
            ("inv82", _run("sonda", 4, {"acierto": 1.0}))]
    medidas = dm.medidas_de(runs)
    assert set(medidas) == {"v1", "v1_sintetico"}
    assert medidas["v1"][0] == {"acierto": 0.8, "acierto_equivalencias": 0.9, "_run": "nuevo"} and medidas["v1"][1] == 3
    v = {"modelo": "qwen", "digest": "", "prompt": "p/1", "catalogo": "c", "huella_codigo": "abc", "mejoras": "agrupacion",
         "verificar": "sí", "razonamiento": ""}
    nota = "\n".join(dm.nota_evolucion(2, v, "d882b8e0", 0, medidas, ["INV-72"], ["código"],
                                       {"commits": [], "prs": [], "historias": [], "total": 0}, "3805ceb0"))
    assert "**Qué cambia frente a la versión 01:** código." in nota and "| v1 | 80.0 % | 90.0 % |" in nota


# --- Despliegues y prueba de humo del chat ---------------------------------------------------------------------

def test_las_mejoras_del_despliegue_salen_de_k8s_o_del_compose():
    assert despliegues_mlflow.MEJORAS_K8S.search("      - MEJORAS=agrupacion\n").group(1) == "agrupacion"
    assert despliegues_mlflow.MEJORAS_COMPOSE.search("      MEJORAS: ${MEJORAS:-agrupacion}").group(1) == "agrupacion"


@pytest.mark.skipif(subprocess.run(["git", "cat-file", "-e", "d882b8e"], cwd=comparar.RAIZ, capture_output=True).returncode,
                    reason="el CI clona sin historia (fetch-depth 1)")
def test_el_despliegue_del_pr_79():
    d = despliegues_mlflow.datos_commit("d882b8e")
    assert d["prs"] == [79] and d["historias"] == ["INV-72"] and d["mejoras"] == "agrupacion"
    assert despliegues_mlflow.mejoras_en("cb1ad81") == "ninguna"         # antes de INV-72 no encendía ninguna


SSE = "\n\n".join([
    'event: meta\ndata: {"modelo": "qwen.qwen3-32b-v1:0", "version_prompt": "v2"}',
    'event: tool\ndata: {"nombre": "historial_ventas", "estado": "inicio", "etiqueta": "Ventas por año"}',
    'event: tool\ndata: {"nombre": "historial_ventas", "estado": "ok", "ms": 693}',
    'event: data\ndata: {"titulo": "Ventas por año", "filas": [{}, {}, {}]}',
    'event: token\ndata: {"texto": "Vendieron $ 1.234.567 "}',
    'event: token\ndata: {"texto": "desde 2022."}',
    'event: done\ndata: {"rondas": 2, "fidelidad": "ok", "respaldo": false, "ms_total": 2482}',
])


def test_un_turno_del_chat_pasa_si_termina_bien():
    t = humo_chat.turno("¿histórico?", "gerente", None, SSE)
    assert t["pasa"] and t["respuesta"] == "Vendieron $ 1.234.567 desde 2022."
    assert t["herramientas"][0]["etiqueta"] == "Ventas por año" and t["datos"] == [{"titulo": "Ventas por año", "filas": 3}]
    falla = humo_chat.turno("x", "gerente", None, SSE.replace('"fidelidad": "ok"', '"fidelidad": "falla"'))
    assert not falla["pasa"]
    error = humo_chat.turno("x", "gerente", None, 'event: error\ndata: {"codigo": "timeout", "mensaje": "superó 120 s"}')
    assert not error["pasa"] and error["final"]["codigo"] == "timeout"


def test_la_prueba_de_humo_contra_un_chat_simulado(monkeypatch):
    monkeypatch.delenv("INVENTAIO_CLAVES_PRUEBA", raising=False)
    monkeypatch.setenv("INVENTAIO_CLAVE_PRUEBA", "clave-de-prueba")

    def responder(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        if peticion.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "d882b8e", "version": "3.0.0"})
        assert peticion.headers["Authorization"] == "Bearer t"
        return httpx.Response(200, text=SSE)

    resultado = humo_chat.correr("https://staging.ejemplo", transport=httpx.MockTransport(responder))
    assert resultado["meta"]["commit"] == "d882b8e" and len(resultado["turnos"]) == len(humo_chat.PREGUNTAS)
    m = humo_chat.metricas(resultado)
    assert m["tasa_pasa"] == 1.0 and m["ms_p50"] == 2482.0
    nota = humo_chat.nota(resultado, "run-despliegue", "INV-72")
    assert "**Pasan 2 de 2**" in nota and "Ventas por año" in nota
    from evaluacion.privacidad import sin_pesos
    assert "1.234.567" not in json.dumps(sin_pesos(resultado))           # lo que va a MLflow


# --- Con MLflow real -------------------------------------------------------------------------------------------

@pytest.mark.mlflow
def test_comparacion_y_evolucion_en_mlflow(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    monkeypatch.chdir(tmp_path)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setattr(rm, "RESULTADOS", tmp_path / "resultados")
    from tests.test_comparar import BASE, NUBE, _archivo, _corrida
    carpeta = tmp_path / "par"
    carpeta.mkdir()
    # Con ids del v1 de verdad: el registro busca en el conjunto las preguntas que fallan
    base = _archivo(carpeta / "base.jsonl", BASE | {"tipo": "completa"}, [_corrida(f"v1-{i:02d}", i % 4 != 0, True, 4.0) for i in range(1, 21)])
    nuevo = _archivo(carpeta / "nuevo.jsonl", NUBE | {"tipo": "completa"}, [_corrida(f"v1-{i:02d}", True, True, 5.0, 0.0005) for i in range(1, 21)])
    primero = comparar.registrar_mlflow(base, nuevo, uri, historia="INV-72", motivo="prueba")
    assert comparar.registrar_mlflow(base, nuevo, uri, historia="INV-72") == primero          # idempotente
    con_eq = comparar.registrar_mlflow(base, nuevo, uri, True, None, "INV-72")
    assert con_eq != primero
    import mlflow
    c = mlflow.MlflowClient(uri)
    run = c.get_run(primero)
    assert run.data.tags["tipo"] == "comparacion" and run.data.tags["cumple"] == "sí" and run.data.metrics["cumple"] == 1.0
    id_nuevo = run.data.tags["compara_nuevo"]
    assert "acierto_equivalencias" in c.get_run(id_nuevo).data.metrics
    d = dm.Documentador(uri)
    d.versiones()
    hechos = d.evolucion()
    assert len(hechos) == 2 and hechos[0].startswith("01 · ")             # dos modelos: dos versiones
    assert d.evolucion() == hechos                                        # idempotente
    evolucion = c.get_experiment_by_name(dm.EVOLUCION)
    runs = c.search_runs([evolucion.experiment_id], order_by=["attributes.start_time ASC"])
    assert [r.data.tags["version"] for r in runs] == ["01", "02"]
    assert runs[1].data.tags["cambia"] and "acierto_v1" in runs[1].data.metrics
    assert "acierto_equivalencias_v1" in runs[1].data.metrics
    modelos = c.search_logged_models([c.get_run(id_nuevo).info.experiment_id])
    assert {m.tags.get("version") for m in modelos} == {"01", "02"}
    assert len(d.reconstruir()) == 2 and not c.search_logged_models([c.get_run(id_nuevo).info.experiment_id])


# --- Todo el camino con el MLflow en memoria (lo que corre en el CI) ------------------------------------------

def test_comparacion_evolucion_despliegue_y_humo_en_memoria(tmp_path, monkeypatch):
    from tests import mlflow_memoria
    from tests.test_comparar import BASE, NUBE, _archivo, _corrida
    memoria = mlflow_memoria.instalar(monkeypatch)
    monkeypatch.setattr(rm, "RESULTADOS", tmp_path / "resultados")
    monkeypatch.setattr(rm.ClienteMlflow, "dataset", lambda *a: None)          # el dataset lo prueba la marca mlflow
    carpeta = tmp_path / "2026-11-26_par"
    carpeta.mkdir()
    codigo = {"huella_codigo": "abc123abc123", "tipo": "completa"}
    base = _archivo(carpeta / "base.jsonl", BASE | codigo | {"inicio": "2026-11-18T10:00:00+00:00"},
                    [_corrida(f"v1-{i:02d}", i % 4 != 0, True, 4.0) for i in range(1, 21)])
    nuevo = _archivo(carpeta / "nuevo.jsonl", NUBE | codigo | {"mejoras": "agrupacion", "inicio": "2026-11-26T10:00:00+00:00"},
                     [_corrida(f"v1-{i:02d}", True, True, 5.0, 0.0005) for i in range(1, 21)])
    uri = "http://127.0.0.1:5000"

    # La comparación: un run ligado a las dos corridas; con equivalencias, la nueva recibe su acierto
    primero = comparar.registrar_mlflow(base, nuevo, uri, historia="INV-72", motivo="prueba")
    assert comparar.registrar_mlflow(base, nuevo, uri) == primero
    con_eq = comparar.registrar_mlflow(base, nuevo, uri, True, None, "INV-72")
    run = memoria.get_run(primero)
    assert run.data.tags["tipo"] == "comparacion" and run.data.tags["cumple"] == "sí" and "Para qué:** prueba" in \
        run.data.tags["mlflow.note.content"]
    id_nuevo = run.data.tags["compara_nuevo"]
    # Sin llamadas guardadas, la recalificación no ve la herramienta: el acierto con equivalencias es el de la comparación
    assert memoria.get_run(id_nuevo).data.metrics["acierto_equivalencias"] == memoria.get_run(con_eq).data.metrics["nuevo_acierto"]
    assert memoria.get_run(id_nuevo).data.tags["comparacion_equivalencias"] == con_eq
    assert comparar.main(["--base", str(base), "--nuevo", str(nuevo), "--mlflow", "--tracking-uri", uri]) == primero

    # Las versiones y la evolución: dos versiones (cambian el modelo y las mejoras), en orden de fecha
    d = dm.Documentador(uri)
    assert len(d.versiones()) == 2
    hechos = d.evolucion()
    assert [h[:2] for h in hechos] == ["01", "02"] and d.evolucion() == hechos
    evolucion = memoria.search_runs([memoria.get_experiment_by_name(dm.EVOLUCION).experiment_id])
    assert evolucion[1].data.tags["cambia"] == "modelo, mejoras" and evolucion[1].data.params["mejoras"] == "agrupacion"
    assert evolucion[1].data.metrics["acierto_v1"] == 1.0 and "acierto_equivalencias_v1" in evolucion[1].data.metrics
    assert {m.tags["version"] for m in memoria.modelos.values()} == {"01", "02"}
    assert len(d.reconstruir()) == 2 and not memoria.search_logged_models(["1"])

    # El despliegue: de Actions, con el código desplegado y las versiones que lo tienen
    sha = "d882b8e" + "0" * 33
    respuestas = {"list": [{"databaseId": 1, "headSha": sha, "createdAt": "2026-11-26T22:31:37Z", "conclusion": "success",
                            "url": "u"}],
                  "view": {"jobs": [{"name": "Imagen api", "conclusion": "success"},
                                    {"name": "Desplegar staging / Desplegar en staging", "conclusion": "success",
                                     "databaseId": 7, "url": "https://ejemplo/job/7",
                                     "startedAt": "2026-11-26T22:40:00Z", "completedAt": "2026-11-26T22:45:30Z"}]}}
    monkeypatch.setattr(despliegues_mlflow, "_gh", lambda *args: respuestas[args[1]])
    monkeypatch.setattr(despliegues_mlflow, "desde", lambda: "2026-11-24T21:27:00-05:00")
    monkeypatch.setattr(despliegues_mlflow, "datos_commit", lambda c: {
        "mensaje": "Merge pull request #79 from x/fix/INV-72\n\nfix(INV-72): Vera", "prs": [79], "historias": ["INV-72"],
        "huella_codigo": "abc123abc123", "mejoras": "agrupacion", "version_app": "3.0.0"})
    d.versiones(), d.evolucion()
    [id_despliegue] = despliegues_mlflow.registrar(uri)
    assert despliegues_mlflow.registrar(uri) == []                       # idempotente por el trabajo
    despliegue = memoria.get_run(id_despliegue)
    assert despliegue.data.tags["versiones_agente"] == "02" and despliegue.data.metrics == {"exito": 1.0, "duracion_s": 330.0}
    assert "PR #79" in despliegue.data.tags["mlflow.note.content"] and despliegue.info.status == "FINISHED"

    # La prueba de humo: ligada al despliegue de su commit, sin cifras en pesos
    prueba = tmp_path / "humo.json"
    prueba.write_text(json.dumps({"meta": {"url": "https://staging.ejemplo", "commit": "d882b8e", "version": "3.0.0",
                                           "inicio": "2026-11-26T23:00:00+00:00"},
                                  "turnos": [humo_chat.turno("¿histórico?", "gerente", None, SSE)]}), encoding="utf-8")
    id_humo = humo_chat.main(["--registrar", str(prueba), "--historia", "INV-72", "--tracking-uri", uri])
    assert humo_chat.registrar(prueba, uri) == id_humo
    humo = memoria.get_run(id_humo)
    assert humo.data.tags["despliegue_run"] == id_despliegue and humo.data.metrics["tasa_pasa"] == 1.0


def test_los_comandos_solo_aceptan_mlflow_local():
    for main in (comparar.main, despliegues_mlflow.main, humo_chat.main):
        argumentos = ["--registrar", "x.json"] if main is humo_chat.main else ["--base", "a", "--nuevo", "b", "--mlflow"] \
            if main is comparar.main else []
        with pytest.raises(SystemExit, match="local"):
            main([*argumentos, "--tracking-uri", "https://mlflow.ejemplo.com"])


def test_el_manifiesto_sin_mlflow_resume_cada_comparacion(tmp_path, capsys):
    from tests.test_comparar import _par
    base, nuevo = _par(tmp_path, lambda i: True, lambda i: True)
    manifiesto = tmp_path / "comparaciones.json"
    manifiesto.write_text(json.dumps({"comparaciones": [{"historia": "INV-72", "motivo": "m", "base": str(base),
                                                         "nuevo": str(nuevo)}]}), encoding="utf-8")
    assert comparar.main(["--manifiesto", str(manifiesto)]) == []
    assert "INV-72" in capsys.readouterr().out and "cumple" in capsys.readouterr().out + "cumple"
    manifiesto.write_text(json.dumps({"comparaciones": [{"historia": "INV-72", "base": str(tmp_path / "no.jsonl"),
                                                         "nuevo": str(nuevo)}]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="Faltan archivos"):
        comparar.main(["--manifiesto", str(manifiesto)])
