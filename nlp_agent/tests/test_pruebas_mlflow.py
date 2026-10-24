"""Lectura de los reportes de pytest y newman que se registran en MLflow (INV-33, decisión M1)."""
from evaluacion import pruebas_mlflow as pm

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
