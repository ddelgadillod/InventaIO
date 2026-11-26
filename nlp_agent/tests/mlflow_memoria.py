"""
INV-72 — Un MLflow en memoria para el CI (MLflow no se instala en el CI): experimentos, runs con sus búsquedas,
versiones del agente (logged models) y las entidades que usan `comparar`, `documentar_mlflow`,
`despliegues_mlflow` y `humo_chat`. Las pruebas contra MLflow real siguen con la marca `mlflow`.
"""
import re
import sys
import types
from types import SimpleNamespace

FILTRO = re.compile(r"(tags|params)\.`?([\w.]+)`?\s*=\s*'([^']*)'")


def _cumple(objeto, filtro: str | None) -> bool:
    for donde, clave, valor in FILTRO.findall(filtro or ""):
        if getattr(objeto, donde).get(clave) != valor:
            return False
    return True


class Run(SimpleNamespace):
    @property
    def tags(self):
        return self.data.tags

    @property
    def params(self):
        return self.data.params


class MlflowMemoria:
    def __init__(self):
        self.experimentos, self.runs, self.modelos, self.artefactos = {}, {}, {}, []

    # --- Experimentos ---
    def get_experiment_by_name(self, nombre):
        return next((e for e in self.experimentos.values() if e.name == nombre), None)

    def create_experiment(self, nombre, tags=None):
        exp_id = str(len(self.experimentos) + 1)
        self.experimentos[exp_id] = SimpleNamespace(experiment_id=exp_id, name=nombre, tags=dict(tags or {}))
        return exp_id

    def set_experiment_tag(self, exp_id, clave, valor):
        self.experimentos[exp_id].tags[clave] = valor

    # --- Runs ---
    def create_run(self, exp_id, start_time=None, run_name=None, tags=None):
        run_id = f"run{len(self.runs)}"
        self.runs[run_id] = Run(
            info=SimpleNamespace(run_id=run_id, experiment_id=exp_id, start_time=start_time or 1, end_time=None,
                                 run_name=run_name, status="RUNNING", borrado=False),
            data=SimpleNamespace(tags=dict(tags or {}), params={}, metrics={}),
            inputs=SimpleNamespace(model_inputs=[], dataset_inputs=[]))
        return self.runs[run_id]

    def get_run(self, run_id):
        return self.runs[run_id]

    def search_runs(self, exp_ids, filter_string=None, max_results=None, order_by=None):
        runs = [r for r in self.runs.values() if r.info.experiment_id in exp_ids and not r.info.borrado
                and _cumple(r.data, filter_string)]
        return sorted(runs, key=lambda r: r.info.start_time or 0, reverse=bool(order_by and "DESC" in order_by[0]))

    def log_batch(self, run_id, metrics=(), params=(), tags=()):
        r = self.runs[run_id]
        for p in params:
            if p.key in r.data.params and r.data.params[p.key] != p.value:
                raise ValueError(f"el parámetro {p.key} ya está")             # como MLflow
            r.data.params[p.key] = p.value
        r.data.metrics |= {m.key: m.value for m in metrics}
        r.data.tags |= {t.key: t.value for t in tags}
        if "mlflow.runName" in r.data.tags:
            r.info.run_name = r.data.tags["mlflow.runName"]

    def set_tag(self, run_id, clave, valor):
        self.runs[run_id].data.tags[clave] = valor

    def log_artifact(self, run_id, ruta):
        self.artefactos.append((run_id, ruta))

    def log_inputs(self, run_id, models=None, datasets=None):
        self.runs[run_id].inputs.model_inputs += list(models or [])

    def set_terminated(self, run_id, status=None, end_time=None):
        self.runs[run_id].info.status, self.runs[run_id].info.end_time = status or "FINISHED", end_time

    def delete_run(self, run_id):
        self.runs[run_id].info.borrado = True

    # --- Versiones del agente ---
    def create_logged_model(self, exp_id, name=None, params=None, model_type=None, tags=None):
        model_id = f"m{len(self.modelos)}"
        self.modelos[model_id] = SimpleNamespace(model_id=model_id, experiment_id=exp_id, name=name, params=dict(params or {}),
                                                 tags=dict(tags or {}), metrics=[], borrado=False)
        return self.modelos[model_id]

    def finalize_logged_model(self, model_id, estado):
        pass

    def search_logged_models(self, exp_ids, filter_string=None, max_results=None):
        return [m for m in self.modelos.values() if m.experiment_id in exp_ids and not m.borrado and _cumple(m, filter_string)]

    def get_logged_model(self, model_id):
        return self.modelos[model_id]

    def set_logged_model_tags(self, model_id, tags):
        self.modelos[model_id].tags |= tags

    def delete_logged_model(self, model_id):
        self.modelos[model_id].borrado = True


def instalar(monkeypatch) -> MlflowMemoria:
    """Pone el MLflow en memoria en `sys.modules` mientras dura la prueba."""
    memoria = MlflowMemoria()
    modulo = types.ModuleType("mlflow")
    modulo.MlflowClient = lambda uri=None: memoria
    modulo.set_tracking_uri = lambda uri: None
    modulo.genai = SimpleNamespace(load_prompt=lambda *a, **k: None)
    entidades = types.ModuleType("mlflow.entities")
    entidades.Metric = lambda key, value, timestamp=0, step=0, **otros: SimpleNamespace(key=key, value=value, **otros)
    entidades.Param = lambda key, value: SimpleNamespace(key=key, value=value)
    entidades.RunTag = lambda key, value: SimpleNamespace(key=key, value=value)
    entidades.LoggedModelInput = lambda model_id: SimpleNamespace(model_id=model_id)
    modulo.entities = entidades
    monkeypatch.setitem(sys.modules, "mlflow", modulo)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entidades)
    return memoria
