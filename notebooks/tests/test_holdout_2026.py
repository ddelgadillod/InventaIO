"""INV-63 — Pruebas del holdout 2026 con datos sintéticos (P1 a P8 y P10 de docs/INV-63-requerimientos.md).
Ninguna usa datos del negocio. Correr desde la raíz: python -m pytest notebooks/tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import holdout_2026 as h  # noqa: E402


def _ic(mejora, bajo, alto):
    return dict(mejora_rel=mejora, ic_bajo=bajo, ic_alto=alto)


# ── P1 y P2: orígenes ────────────────────────────────
def test_origenes_empiezan_en_el_primer_dia_habil_y_avanzan_cada_15():
    # 1-ene sin ventas (hueco global): el primer día hábil es el 2
    fechas = pd.date_range("2025-12-20", "2026-03-31").drop(pd.Timestamp("2026-01-01"))
    origenes = h.origenes_holdout(fechas)
    habiles_2026 = fechas[fechas >= "2026-01-01"]
    assert origenes[0] == pd.Timestamp("2026-01-02")
    assert all(habiles_2026.get_loc(b) - habiles_2026.get_loc(a) == 15 for a, b in zip(origenes, origenes[1:]))


def test_origenes_se_detienen_si_la_ventana_no_esta_completa():
    fechas = pd.date_range("2026-01-02", periods=46)       # índices 0..45
    origenes = h.origenes_holdout(fechas)
    # 0 y 15 tienen 15 días después; 30 también (30+15 = 45, el último); 45 ya no
    assert list(origenes) == [fechas[0], fechas[15], fechas[30]]


@pytest.mark.parametrize("n, esperado", [(7, "indicio"), (8, "veredicto"), (18, "veredicto")])
def test_con_menos_de_8_origenes_es_indicio(n, esperado):
    assert h.estado_resultado(n) == esperado


def test_un_indicio_no_activa_acciones():
    reglas = [h.regla_r2(_ic(-0.2, -0.3, -0.1))]
    assert h.veredicto_global(reglas, "indicio") == dict(veredicto="indicio", acciones=[])


# ── P3: R1 ───────────────────────────────────────────
def test_r1_confirmada_solo_con_ic_bajo_positivo():
    assert h.regla_r1(_ic(0.05, 0.01, 0.09))["estado"] == "confirmada"
    r = h.regla_r1(_ic(0.02, -0.01, 0.05))
    assert r["estado"] == "no_confirmada" and r["accion"]


# ── P4: R2 ───────────────────────────────────────────
def test_r2_tres_casos():
    assert h.regla_r2(_ic(0.07, 0.05, 0.09))["estado"] == "confirmada"
    cruza = h.regla_r2(_ic(0.01, -0.02, 0.04))
    assert cruza["estado"] == "ic_cruza_cero" and cruza["cumple"] and cruza["accion"] is None
    falla = h.regla_r2(_ic(-0.05, -0.08, -0.02))
    assert not falla["cumple"] and "baseline_cuantil" in falla["accion"]


# ── P5: R3 ───────────────────────────────────────────
def test_r3_estrato_chico_es_insuficiente_y_no_decide():
    r = h.regla_r3([
        dict(rama="intermitente", estrato=None, n_filas=5000, cobertura=0.90, alpha=0.893),
        dict(rama="intermitente", estrato="cabeza", n_filas=150, cobertura=0.70, alpha=0.893),
    ])
    assert r["cumple"]
    assert r["detalle"].set_index("estrato", drop=False).loc["cabeza", "resultado"] == "insuficiente"


def test_r3_desvio_mayor_a_005_dispara_la_reestimacion_de_esa_rama():
    r = h.regla_r3([
        dict(rama="intermitente", estrato=None, n_filas=5000, cobertura=0.90, alpha=0.893),
        dict(rama="suave_perecedero", estrato=None, n_filas=900, cobertura=0.25, alpha=0.167),
    ])
    assert not r["cumple"] and r["ramas_que_fallan"] == ["suave_perecedero"]
    assert "razones de la rama suave_perecedero" in r["accion"]


# ── P6: R4 ───────────────────────────────────────────
def _estratos(cal, sin, n=(500, 500, 500)):
    return [dict(estrato=e, n_filas=k, cobertura_cal=c, cobertura_sin_cal=s)
            for e, k, c, s in zip(("cabeza", "medio", "cola"), n, cal, sin)]


def test_r4_cumple_con_2_de_3_mas_cerca_y_costo_no_peor():
    r = h.regla_r4(_estratos((0.89, 0.90, 0.80), (0.85, 0.84, 0.88)), _ic(0.0, -0.01, 0.01))
    assert r["cumple"] and r["estratos_mas_cerca"] == 2


def test_r4_se_desactiva_si_el_costo_empeora_o_no_acerca_la_cobertura():
    peor_costo = h.regla_r4(_estratos((0.89, 0.90, 0.89), (0.85, 0.84, 0.85)), _ic(-0.05, -0.08, -0.02))
    assert not peor_costo["cumple"] and "desactiva" in peor_costo["accion"]
    no_acerca = h.regla_r4(_estratos((0.80, 0.90, 0.80), (0.89, 0.84, 0.89)), _ic(0.0, -0.01, 0.01))
    assert not no_acerca["cumple"]


def test_r4_solo_cuenta_estratos_evaluables():
    r = h.regla_r4(_estratos((0.89, 0.89, 0.80), (0.85, 0.85, 0.88), n=(100, 500, 500)), _ic(0.0, -0.01, 0.01))
    assert r["estratos_evaluables"] == 2 and r["estratos_mas_cerca"] == 1 and not r["cumple"]


def test_veredicto_confirmado_solo_si_todas_confirmadas():
    ok = [h.regla_r1(_ic(0.05, 0.01, 0.09)), h.regla_r2(_ic(0.07, 0.05, 0.09))]
    assert h.veredicto_global(ok, "veredicto")["veredicto"] == "politica_confirmada"
    sin_confirmar = [h.regla_r1(_ic(0.02, -0.01, 0.05)), h.regla_r2(_ic(0.01, -0.02, 0.04))]
    v = h.veredicto_global(sin_confirmar, "veredicto")
    assert v["veredicto"] == "con_acciones" and v["acciones"] == ["R1: se reevalua en el reentrenamiento (INV-62)"]


# ── P7: universo D1 ─────────────────────────────────
def test_universo_d1_solo_pares_con_el_producto_en_los_inventarios():
    filas = pd.DataFrame({"codigo_item": ["001", "002", "003", "001"], "sucursal": ["A", "A", "B", "B"]})
    sub = h.universo_d1(filas, {"001", "003"})
    assert sorted(set(sub["codigo_item"])) == ["001", "003"] and len(sub) == 3


# ── P8: compuertas de huellas ───────────────────────
def test_verificar_huellas_detecta_un_byte_distinto(tmp_path):
    (tmp_path / "models").mkdir()
    archivo = tmp_path / "models" / "m.joblib"
    archivo.write_bytes(b"modelo")
    import hashlib
    esperado = {"models/m.joblib": hashlib.sha256(b"modelo").hexdigest()}
    assert h.verificar_huellas(esperado, tmp_path) == []
    archivo.write_bytes(b"modelO")
    assert h.verificar_huellas(esperado, tmp_path) == ["models/m.joblib"]


def test_huella_filas_ignora_el_orden_y_las_filas_posteriores_al_corte():
    base = pd.DataFrame({
        "codigo_item": ["001", "002", "001"], "sucursal": ["A", "A", "B"],
        "fecha_origen": pd.to_datetime(["2025-12-12", "2025-11-20", "2026-01-02"]),
        "trail_15": np.array([1.0, 2.0, 3.0], dtype="float32"),
    })
    otra = base.iloc[[2, 1, 0]][["trail_15", "fecha_origen", "sucursal", "codigo_item"]]
    assert h.huella_filas(base, "2025-12-12") == h.huella_filas(otra, "2025-12-12")
    assert h.huella_filas(base, "2025-12-12")[0] == 2
    cambiada = base.copy()
    cambiada.loc[0, "trail_15"] = 1.5
    assert h.huella_filas(cambiada, "2025-12-12") != h.huella_filas(base, "2025-12-12")


# ── P10: evaluación de un universo ya predicho ──────
def _filas_sinteticas(n_productos=60, sesgo_modelo=0.0, semilla=0):
    rng = np.random.default_rng(semilla)
    filas = []
    for i in range(n_productos):
        rama = ("intermitente", "suave_no_perecedero", "suave_perecedero")[i % 3]
        estrato = ("cabeza", "medio", "cola")[(i // 3) % 3]
        alpha = 0.167 if rama == "suave_perecedero" else 0.893
        for origen in range(10):
            y = float(rng.poisson(5))
            piso = y + rng.normal(0, 3)
            p50 = y + rng.normal(sesgo_modelo, 1)
            pneg = p50 + (4 if alpha > 0.5 else -2)
            filas.append(dict(codigo_item=f"{i:03d}", rama=rama, estrato=estrato, alpha=alpha, y=y, p50=p50, piso=piso,
                              cubre=y <= pneg, costo_modelo=abs(y - pneg) * 0.1, costo_ref=abs(y - pneg) * 0.2,
                              cubre_sin_cal=y <= p50, costo_sin_cal=abs(y - p50) * 0.3))
    return pd.DataFrame(filas)


def test_evaluar_universo_arma_las_cuatro_reglas_con_sus_entradas():
    r = h.evaluar_universo(_filas_sinteticas(), n_origenes=10, B=200)
    r1, r2, r3, r4 = r["reglas"]
    assert [x["regla"] for x in r["reglas"]] == ["R1", "R2", "R3", "R4"] and r["estado"] == "veredicto"
    assert r1["estado"] == "confirmada"                        # el q50 erra menos que el piso
    assert r2["estado"] == "confirmada" and abs(r2["mejora_rel"] - 0.5) < 1e-9   # costo 0,1 frente a 0,2
    assert set(r3["detalle"]["rama"]) == {"intermitente", "suave_no_perecedero", "suave_perecedero"}
    assert r3["detalle"]["estrato"].isna().sum() == 3          # una fila por rama completa
    assert r4["estratos_evaluables"] == 0 and not r4["cumple"]  # unos 7 productos x 10 orígenes por estrato < 200 filas


def test_evaluar_universo_con_pocos_origenes_no_activa_acciones():
    r = h.evaluar_universo(_filas_sinteticas(sesgo_modelo=6.0), n_origenes=5, B=200)
    assert r["estado"] == "indicio" and r["veredicto"] == "indicio" and r["acciones"] == []
