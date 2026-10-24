"""
INV-33 — Un MLflow simulado para el CI (M2 de INV-31: MLflow no se instala en el CI).

Reemplaza el paquete `mlflow` en `sys.modules` con lo que usan `trazas_mlflow.py` y `pruebas_mlflow.py`: el cliente
(runs, trazas y spans), las evaluaciones y las entidades. Guarda cada llamada para revisarla; las pruebas con
MLflow real siguen con la marca `mlflow`.
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace


class MlflowFalso:
    def __init__(self):
        self.uri = None
        self.experimentos, self.etiquetas_experimento = {}, {}
        self.runs, self.trazas, self.evaluaciones = {}, {}, []

    # --- Cliente: experimentos y runs ---
    def get_experiment_by_name(self, nombre):
        return SimpleNamespace(experiment_id=self.experimentos[nombre]) if nombre in self.experimentos else None

    def create_experiment(self, nombre, tags=None):
        self.experimentos[nombre] = f"exp{len(self.experimentos)}"
        return self.experimentos[nombre]

    def set_experiment_tag(self, experimento, clave, valor):
        self.etiquetas_experimento[(experimento, clave)] = valor

    def create_run(self, experimento, start_time=None, run_name=None):
        run_id = f"run{len(self.runs)}"
        self.runs[run_id] = {"exp": experimento, "nombre": run_name, "inicio": start_time, "metricas": {},
                             "params": {}, "tags": {}, "artefactos": []}
        return SimpleNamespace(info=SimpleNamespace(run_id=run_id))

    def get_run(self, run_id):
        return SimpleNamespace(info=SimpleNamespace(experiment_id=self.runs.get(run_id, {}).get("exp", "exp0")))

    def log_batch(self, run_id, metrics=(), params=(), tags=()):
        r = self.runs[run_id]
        r["metricas"] |= {m.key: m.value for m in metrics}
        r["params"] |= {p.key: p.value for p in params}
        r["tags"] |= {t.key: t.value for t in tags}

    def log_artifact(self, run_id, ruta):
        self.runs[run_id]["artefactos"].append(Path(ruta).name)

    def set_terminated(self, run_id, status=None, end_time=None):
        self.runs[run_id] |= {"estado": status, "fin": end_time}

    # --- Cliente: trazas ---
    def search_traces(self, experimentos, filter_string=None, max_results=None, flush=None, run_id=None):
        clave, _, valor = (filter_string or "").removeprefix("tags.").partition(" = ")
        return [t for t in self.trazas.values() if t["exp"] in experimentos and t["tags"].get(clave) == valor.strip("'")]

    def start_trace(self, nombre, span_type=None, inputs=None, attributes=None, tags=None, experiment_id=None,
                    start_time_ns=None, run_id=None):
        trace_id = f"tr{len(self.trazas)}"
        self.trazas[trace_id] = {"nombre": nombre, "exp": experiment_id, "run": run_id, "tags": tags or {},
                                 "entradas": inputs, "spans": [span_type]}
        return SimpleNamespace(trace_id=trace_id, span_id=f"{trace_id}-raiz")

    def start_span(self, nombre, trace_id=None, parent_id=None, span_type=None, inputs=None, start_time_ns=None,
                   attributes=None):
        self.trazas[trace_id]["spans"].append(span_type)
        return SimpleNamespace(span_id=f"{trace_id}-{len(self.trazas[trace_id]['spans'])}")

    def end_span(self, trace_id, span_id, outputs=None, end_time_ns=None):
        pass

    def end_trace(self, trace_id, outputs=None, status=None, end_time_ns=None):
        self.trazas[trace_id] |= {"salida": outputs, "estado": status}

    # --- Módulo: evaluaciones de las trazas ---
    def set_tracking_uri(self, uri):
        self.uri = uri

    def flush_trace_async_logging(self):
        pass

    def log_feedback(self, trace_id, name, value, source=None, rationale=None):
        self.evaluaciones.append((trace_id, "feedback", name, value))

    def log_expectation(self, trace_id, name, value):
        self.evaluaciones.append((trace_id, "expectativa", name, value))


def instalar(monkeypatch) -> MlflowFalso:
    """Pone el MLflow simulado en `sys.modules` mientras dura la prueba."""
    falso = MlflowFalso()
    modulo = types.ModuleType("mlflow")
    modulo.MlflowClient = lambda uri=None: falso
    for nombre in ("set_tracking_uri", "flush_trace_async_logging", "log_feedback", "log_expectation"):
        setattr(modulo, nombre, getattr(falso, nombre))
    entidades = types.ModuleType("mlflow.entities")
    entidades.AssessmentSource = lambda source_type, source_id: SimpleNamespace(tipo=source_type, id=source_id)
    entidades.Metric = lambda key, value, timestamp, step: SimpleNamespace(key=key, value=value)
    entidades.Param = lambda key, value: SimpleNamespace(key=key, value=value)
    entidades.RunTag = lambda key, value: SimpleNamespace(key=key, value=value)
    modulo.entities = entidades
    monkeypatch.setitem(sys.modules, "mlflow", modulo)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entidades)
    return falso
