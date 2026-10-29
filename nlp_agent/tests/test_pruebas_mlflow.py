"""Lectura de los reportes de pytest y newman que se registran en MLflow (INV-33, decisión M1)."""
import json
import sys
from pathlib import Path

import pytest

from evaluacion import pruebas_mlflow as pm
from tests.mlflow_falso import instalar

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" errors="0" failures="1"
skipped="2" tests="10" time="3.5"><testcase classname="tests.test_a" name="test_ok" time="0.1"/>
<testcase classname="tests.test_a" name="test_mal" time="0.1"><failure message="assert 1 == 2">detalle</failure>
</testcase></testsuite></testsuites>"""

NEWMAN = {"collection": {"info": {"name": "InventaIO · INV-33"}},
          "run": {"stats": {"requests": {"total": 2, "failed": 0}, "assertions": {"total": 3, "failed": 1}},
                  "timings": {"started": 1000, "completed": 4200},
                  "executions": [{"item": {"name": "VP-01"}, "response": {"code": 200, "stream": "cifras reales"},
                                  "assertions": [{"assertion": "Responde 200"}, {"assertion": "Total", "error": {"message": "x"}}]}],
                  "failures": [{"source": {"name": "VP-01"}, "error": {"test": "Total", "message": "expected 1"}}]}}


def test_junit():
    r = pm.leer_junit(JUNIT)
    assert r["metricas"] == {"pruebas": 10, "pasadas": 7, "fallidas": 1, "errores": 0, "omitidas": 2, "duracion_s": 3.5}
    assert r["fallas"] == ["tests.test_a::test_mal — assert 1 == 2"]


def test_newman_sin_las_respuestas():
    r = pm.leer_newman(NEWMAN)
    assert r["metricas"] == {"peticiones": 2, "peticiones_fallidas": 0, "verificaciones": 3, "verificaciones_fallidas": 1,
                             "duracion_s": 3.2}
    assert r["fallas"] == ["VP-01 — Total"]
    assert "cifras reales" not in str(r["resumen"])
    assert r["resumen"]["ejecuciones"][0]["verificaciones"][1] == {"nombre": "Total", "ok": False}


def test_nota_con_fallas():
    r = {"suite": "nlp_agent", "entorno": "pytest local", "comando": "pytest -q", "fallas": ["a::b — x"],
         **{"metricas": pm.leer_junit(JUNIT)["metricas"]}}
    texto = pm.nota(r, {"commit": "abc1234def", "rama": "feature/x", "sucio": True}, "INV-33")
    assert "10 pruebas: 7 pasan, 1 fallan" in texto and "`abc1234` en `feature/x` (con cambios sin commit)" in texto
    assert "- a::b — x" in texto


# --- Las suites y el registro, con los comandos y MLflow simulados (corren en el CI; M2 de INV-31) ---

def test_correr_devuelve_codigo_y_salida(tmp_path):
    codigo, salida = pm._correr([sys.executable, "-c", "print('hola')"], tmp_path)
    assert codigo == 0 and "hola" in salida


def test_suites_leen_sus_reportes(tmp_path, monkeypatch):
    def correr(comando, cwd):
        texto = " ".join(comando)
        if "newman" in texto:
            Path(texto.split("--reporter-json-export ")[1].strip()).write_text(json.dumps(NEWMAN), encoding="utf-8")
        elif "--junitxml=" in texto and "docker" not in texto:
            Path(texto.split("--junitxml=")[1].split()[0]).write_text(JUNIT, encoding="utf-8")
        return 1, "salida"
    monkeypatch.setattr(pm, "_correr", correr)
    monkeypatch.setattr(pm.subprocess, "run", lambda comando, **_: Path(comando[-1]).write_text(JUNIT, encoding="utf-8"))
    nlp = pm.suite_nlp_agent(tmp_path)
    assert nlp["suite"] == "nlp_agent" and nlp["metricas"]["pruebas"] == 10 and nlp["codigo"] == 1
    api = pm.suite_api(tmp_path, "inventaio-api")
    assert api["entorno"] == "contenedor inventaio-api" and api["fallas"] == ["tests.test_a::test_mal — assert 1 == 2"]
    newman = pm.suite_newman(tmp_path, "INV-33", "http://localhost:8000")
    assert newman["suite"] == "newman · INV-33" and newman["metricas"]["verificaciones_fallidas"] == 1
    assert "cifras reales" not in newman["artefactos"][0].read_text(encoding="utf-8")


def test_registrar_un_run_por_suite(tmp_path, monkeypatch):
    falso = instalar(monkeypatch)
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT, encoding="utf-8")
    base = {"entorno": "pytest local", "comando": "pytest -q", "salida": "…", "artefactos": [junit],
            "inicio": 1_000, "fin": 4_000, "metricas": pm.leer_junit(JUNIT)["metricas"]}
    ids = pm.registrar([{**base, "suite": "nlp_agent", "codigo": 0, "fallas": []},
                        {**base, "suite": "newman · INV-33", "codigo": 1, "fallas": ["VP-01 — Total"]}],
                       "sqlite:///simulado.db", "INV-33")
    pasa, falla = (falso.runs[i] for i in ids)
    assert pasa["estado"] == "FINISHED" and pasa["tags"]["resultado"] == "pasa" and pasa["tags"]["historia"] == "INV-33"
    assert falla["estado"] == "FAILED" and falla["tags"]["coleccion"] == "INV-33" and falla["metricas"]["pruebas"] == 10.0
    assert pasa["artefactos"] == ["junit.xml", "salida.txt"] and pasa["params"] == {"comando": "pytest -q"}
    assert pm.registrar([], "sqlite:///simulado.db", None) == [] and len(falso.experimentos) == 1   # reusa el experimento


def test_main_corre_las_suites_pedidas(monkeypatch):
    corridas, registradas = [], []
    resultado = {"entorno": "x", "comando": "x", "salida": "", "artefactos": [], "metricas": {}, "fallas": []}
    monkeypatch.setattr(pm, "suite_nlp_agent", lambda tmp: corridas.append("nlp") or {**resultado, "suite": "nlp_agent", "codigo": 0})
    monkeypatch.setattr(pm, "suite_api", lambda tmp, c: corridas.append(c) or {**resultado, "suite": "api", "codigo": 0})
    monkeypatch.setattr(pm, "suite_newman", lambda tmp, c, url: corridas.append(c) or {**resultado, "suite": c, "codigo": 1})
    monkeypatch.setattr(pm, "registrar", lambda r, uri, historia: registradas.extend(r))
    assert pm.main(["--suites", "nlp_agent,api", "--tracking-uri", "sqlite:///x.db"]) == 0
    assert pm.main(["--suites", "newman", "--colecciones", "INV-33,INV-28", "--tracking-uri", "sqlite:///x.db"]) == 1
    assert corridas == ["nlp", "inventaio-api", "INV-33", "INV-28"] and all(r["fin"] >= r["inicio"] for r in registradas)
    with pytest.raises(SystemExit):
        pm.main(["--tracking-uri", "https://mlflow.externo.example"])
