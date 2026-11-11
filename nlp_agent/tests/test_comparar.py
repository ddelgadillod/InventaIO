"""INV-67 (B13): comparación pareada con la línea base, costo en el reporte y en MLflow."""
import json

from evaluacion import comparar, reporte
from evaluacion import registro_mlflow as rm
from tests.test_registro_mlflow import ClienteFalso


def _corrida(id_, acierto, herramienta, s, costo=None):
    c = {"id": id_, "corrida": 1, "rol": "gerente", "tipo": "consulta", "error": None, "razonamiento_filtrado": False,
         "tokens_prompt_max": 1000, "tokens_respuesta": 50, "ms_total": s * 1000, "llamadas": [], "texto": "",
         "calificacion": {"acierto": acierto, "herramienta": herramienta, "fidelidad": True, "rechazo": True,
                          "hechos": True, "prohibido": True, "aclaracion": True, "sin_error": True,
                          "cifras_sin_respaldo": []}}
    return c | ({"tokens_entrada": 2400, "tokens_salida": 160, "costo_usd": costo} if costo is not None else {})


def _archivo(ruta, meta, corridas):
    ruta.write_text("\n".join(json.dumps(x) for x in [{"meta": True, "corridas": 1, **meta}, *corridas]), encoding="utf-8")
    return ruta


BASE = {"modelo": "qwen3:8b", "modo": "gpu", "entorno": "local", "conjunto": "v1 (real, 20 preguntas)"}
NUBE = {"modelo": "qwen.qwen3-32b-v1:0", "modo": "nube", "entorno": "nube-us-east-1", "conjunto": "v1 (real, 20 preguntas)",
        "proveedor": "bedrock", "region": "us-east-1", "endpoint": "runtime"}


def _par(tmp_path, nuevo_acierto, nuevo_herramienta, s=5.0):
    base = _archivo(tmp_path / "base.jsonl", BASE, [_corrida(f"v1-{i:02d}", i % 4 != 0, True, 4.0) for i in range(20)])
    nuevo = _archivo(tmp_path / "nuevo.jsonl", NUBE, [_corrida(f"v1-{i:02d}", nuevo_acierto(i), nuevo_herramienta(i), s, 0.0005)
                                                      for i in range(20)])
    return base, nuevo


def test_cumple_si_no_empeora_y_p95_en_meta(tmp_path):
    base, nuevo = _par(tmp_path, lambda i: True, lambda i: True)
    texto = comparar.main(["--base", str(base), "--nuevo", str(nuevo)])
    assert "**Regla de B2:** cumple." in texto
    assert "| Costo por pregunta | — | US$0.00050 |" in texto and "| Costo total | — | US$0.01000 |" in texto
    assert "qwen.qwen3-32b-v1:0 (nube, us-east-1)" in texto


def test_no_cumple_si_empeora_la_herramienta(tmp_path):
    base, nuevo = _par(tmp_path, lambda i: i % 4 != 0, lambda i: i % 2 == 0)
    b, n = reporte.leer([base])[0], reporte.leer([nuevo])[0]
    c = comparar.comparar(b, n)
    assert c["empeora"] == ["herramienta"] and not c["cumple"] and c["diferencias"]["acierto"]["diferencia"] == 0
    assert "no cumple (empeora herramienta)" in comparar.markdown(b, n, c)


def test_no_cumple_por_latencia(tmp_path):
    base, nuevo = _par(tmp_path, lambda i: True, lambda i: True, s=45.0)
    texto = comparar.main(["--base", str(base), "--nuevo", str(nuevo)])
    assert "no cumple (p95 de 45.0 s > 30 s)" in texto


def test_el_registro_lleva_proveedor_y_costo(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RESULTADOS", tmp_path)
    carpeta = tmp_path / "2026-11-12_nube-us-east-1"
    carpeta.mkdir()
    _, nuevo = _par(carpeta, lambda i: True, lambda i: True)
    c = ClienteFalso()
    [run_id] = rm.registrar([nuevo], c, historia="INV-67")
    run = c.runs[run_id]
    assert run["params"]["proveedor"] == "bedrock" and run["params"]["region"] == "us-east-1"
    assert run["metricas"]["costo_pregunta_usd"] == 0.0005 and run["metricas"]["costo_total_usd"] == 0.01
    assert "--proveedor bedrock --region us-east-1" in run["tags"]["mlflow.note.content"]


def test_sin_costo_no_hay_metrica(tmp_path):
    base, _ = _par(tmp_path, lambda i: True, lambda i: True)
    r = reporte.resumen(reporte.leer([base])[0]["corridas"])
    assert r["costo_pregunta_usd"] is None and r["costo_total_usd"] is None
