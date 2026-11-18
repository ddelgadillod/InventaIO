"""INV-62 — Pruebas de las funciones del reentrenamiento (sección 7 de docs/INV-62-requerimientos.md), con datos sintéticos.
Ninguna usa datos del negocio. Correr desde la raíz: python -m pytest notebooks/tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reentrenamiento as r  # noqa: E402

HABILES = pd.date_range("2025-11-01", "2025-12-31")


# ── Máscara de demanda censurada ─────────────────────
def test_eventos_solo_con_stock_cero_o_negativo_y_racha_larga():
    foto = pd.DataFrame({"codigo_item": ["A", "B", "C", "D"], "sucursal": "S", "cantidad": [0, -3, 5, 0]})
    ultima = pd.DataFrame({"codigo_item": ["A", "B", "C", "D"], "sucursal": "S",
                           "ultima": pd.to_datetime(["2025-12-01", "2025-11-10", "2025-11-01", "2025-12-29"])})
    ev = r.eventos_censura(foto, ultima, "2025-12-31", HABILES)
    assert sorted(ev["codigo_item"]) == ["A", "B"]          # C tiene stock; D vendió hace 2 días
    assert ev.set_index("codigo_item").loc["A", "racha"] == 30


def test_mascara_solo_la_racha_antes_de_la_foto():
    ev = pd.DataFrame({"codigo_item": ["A"], "sucursal": ["S"], "ultima": [pd.Timestamp("2025-12-01")],
                       "fecha_foto": [pd.Timestamp("2025-12-31")]})
    filas = pd.DataFrame({"codigo_item": ["A", "A", "A", "B"], "sucursal": "S",
                          "fecha_origen": pd.to_datetime(["2025-11-20", "2025-12-05", "2025-12-20", "2025-12-05"]),
                          "fin_ventana": pd.to_datetime(["2025-12-05", "2025-12-20", "2026-01-04", "2025-12-20"])},
                         index=[10, 11, 12, 13])
    assert list(r.mascara_censura(filas, ev)) == [False, True, False, False]
    assert not r.mascara_censura(filas, ev.iloc[0:0]).any()


# ── Estratos al corte ────────────────────────────────
def test_estratos_con_el_acumulado_previo():
    vol = pd.Series([50.0, 20.0, 15.0, 10.0, 5.0, 0.0], index=[("p", str(i)) for i in range(6)])
    e = r.estratos_al_corte(vol)
    assert [e[("p", str(i))] for i in range(6)] == ["cabeza", "medio", "medio", "cola", "cola", "cola"]


def test_estratos_sin_volumen_son_cola():
    e = r.estratos_al_corte(pd.Series([0.0, 0.0], index=["a", "b"]))
    assert set(e.values()) == {"cola"}


# ── Cortes y reglas ──────────────────────────────────
def test_cortes_walk_forward_en_grupos_de_4():
    fechas = pd.date_range("2026-01-01", periods=15, freq="15D")
    cortes = r.cortes_walk_forward(fechas)
    assert len(cortes) == 3 and cortes[0][0] == fechas[3] and cortes[-1][1] == fechas[-1]
    with pytest.raises(ValueError):
        r.cortes_walk_forward(fechas[:5])


def _ic(bajo, alto):
    return dict(mejora_rel=(bajo + alto) / 2, ic_bajo=bajo, ic_alto=alto)


def test_regla_calendario():
    altas = {"a": _ic(0.01, 0.05), "b": _ic(0.02, 0.06), "c": _ic(0.005, 0.04)}
    ok = r.regla_calendario(altas, _ic(-0.01, 0.02), dict(E2=True, E3=True))
    assert ok["entra"]
    una_falla = r.regla_calendario({**altas, "b": _ic(-0.01, 0.03)}, _ic(-0.01, 0.02), dict(E2=True, E3=True))
    assert not una_falla["entra"] and una_falla["temporadas_altas"]["b"] is False
    assert not r.regla_calendario(altas, _ic(-0.03, -0.01), dict(E2=True, E3=True))["entra"]
    assert not r.regla_calendario(altas, _ic(-0.01, 0.02), dict(E2=True, E3=False))["entra"]


# ── Versión de los datos ─────────────────────────────
def test_version_y_datos_nuevos(tmp_path):
    ruta = tmp_path / "fact_ventas.csv"
    ruta.write_text("codigo_item,fecha,cantidad\n001,2026-09-29,1\n002,2026-09-30,2\n")
    v = r.version_datos(ruta)
    assert v[0] == "2026-09-30" and len(v[1]) == 12
    assert r.hay_datos_nuevos(v, None) and not r.hay_datos_nuevos(v, list(v))
    ruta.write_text("codigo_item,fecha,cantidad\n001,2026-09-29,1\n002,2026-10-15,2\n")
    assert r.hay_datos_nuevos(r.version_datos(ruta), v)


# ── Calibración secuencial ───────────────────────────
def test_offsets_usan_solo_origenes_anteriores():
    rng = np.random.default_rng(0)
    residuos = [rng.normal(k * 0.1, 1, 300) for k in range(8)]
    fija = r.offsets_secuenciales(residuos, 0.4, "fija")
    assert fija == [0.4] * 8
    desl = r.offsets_secuenciales(residuos, 0.4, "deslizante", ventana=2)
    assert desl[0] == 0.4                                        # el primero no tiene historia
    assert desl[3] == pytest.approx(r._cuantil_conformal(np.concatenate(residuos[1:3]), 0.893))
    adap = r.offsets_secuenciales(residuos, 0.4, "adaptativa", ventana=2)
    assert len(adap) == 8 and adap[0] == 0.4


def test_adaptativa_sube_el_nivel_si_cubre_de_menos():
    residuos = [np.full(100, 1.0)] * 3 + [np.linspace(0, 2, 100)]
    adap = r.offsets_secuenciales(residuos, -5.0, "adaptativa", ventana=1, gamma=0.5)
    # el primer origen cubre 0 % con el ajuste fijo: el nivel sube y el ajuste del segundo es 1,0
    assert adap[1] == pytest.approx(1.0)


# ── Orquestación con operaciones falsas ──────────────
class Ops:
    def __init__(self, mlflow=True, version=("2026-09-30", "abc"), ultima=None, cumple=True, falla=None):
        self._mlflow, self._version, self._ultima, self._cumple, self._falla = mlflow, version, ultima, cumple, falla
        self.registros, self.exportado = [], False

    def mlflow_ok(self):
        return self._mlflow

    def version(self):
        return self._version

    def ultima_version(self):
        return self._ultima

    def evaluar(self):
        if self._falla == "evaluar":
            raise ValueError("matriz vacía")
        return dict(cumple=self._cumple, E1=self._cumple)

    def exportar(self, evaluacion):
        self.exportado = True
        return "reentrenamiento/20261123"

    def registrar(self, estado, info):
        self.registros.append((estado, info))
        return f"run-{len(self.registros)}"


def test_sin_datos_nuevos_no_entrena():
    ops = Ops(ultima=("2026-09-30", "abc"))
    out = r.orquestar(ops)
    assert out["estado"] == "sin_datos_nuevos" and ops.registros[0][0] == "sin_datos_nuevos" and not ops.exportado


def test_candidato_aceptado_queda_en_su_rama():
    ops = Ops()
    out = r.orquestar(ops)
    assert out["estado"] == "promovible" and out["rama"] == "reentrenamiento/20261123" and ops.exportado


def test_candidato_rechazado_no_se_exporta():
    ops = Ops(cumple=False)
    out = r.orquestar(ops)
    assert out["estado"] == "rechazado" and not ops.exportado and ops.registros[-1][0] == "rechazado"


def test_mlflow_caido_falla_sin_registrar():
    ops = Ops(mlflow=False)
    with pytest.raises(r.MlflowNoResponde):
        r.orquestar(ops)
    assert ops.registros == []


def test_un_error_se_registra_como_fallo_y_se_relanza():
    ops = Ops(falla="evaluar")
    with pytest.raises(ValueError):
        r.orquestar(ops)
    assert ops.registros[-1][0] == "fallo" and "matriz vacía" in ops.registros[-1][1]["error"]
