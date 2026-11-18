"""
INV-62 — Funciones del reentrenamiento programado de la rama intermitente (docs/INV-62-requerimientos.md).

Funciones puras, probadas con datos sintéticos en `notebooks/tests/test_reentrenamiento.py`:
- la máscara de demanda censurada (pares con stock ≤ 0 en una foto y una racha larga sin venta antes de ella);
- los estratos de volumen al corte, con la misma definición que `common_priorizacion.estratos_as_of`;
- los cortes walk-forward de la regla de promoción;
- la regla del calendario de `preregistro_receta_2026.json`;
- la versión de los datos y si hay datos nuevos;
- las variantes de la calibración para la simulación (fija, deslizante y la adaptativa de Gibbs y Candès).
La regla de promoción usa los mismos tres criterios de la exploración (`exploracion_2026.reglas_confirmacion`).
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

RACHA_MINIMA = 15          # días hábiles sin venta antes de una foto con stock ≤ 0 para considerar censurada la racha
NIVEL = 0.893
GAMMA_ADAPTATIVA = 0.05
VENTANA_DESLIZANTE = 6


# ── Máscara de demanda censurada ─────────────────────
def eventos_censura(foto, ultima_venta, fecha_foto, habiles, racha_minima=RACHA_MINIMA):
    """Pares con stock ≤ 0 en la foto que llevaban al menos `racha_minima` días hábiles sin vender antes de ella.
    `foto`: codigo_item, sucursal, cantidad. `ultima_venta`: codigo_item, sucursal, ultima (última venta en o antes de
    la foto). Devuelve codigo_item, sucursal, ultima, fecha_foto y racha (días hábiles después de la última venta)."""
    fecha_foto = pd.Timestamp(fecha_foto)
    sin_stock = foto[foto["cantidad"] <= 0][["codigo_item", "sucursal"]]
    ev = sin_stock.merge(ultima_venta, on=["codigo_item", "sucursal"], how="inner")
    habiles = pd.DatetimeIndex(habiles).values
    fin = np.searchsorted(habiles, np.datetime64(fecha_foto), side="right")
    ev = ev.assign(racha=fin - np.searchsorted(habiles, pd.to_datetime(ev["ultima"]).values, side="right"),
                   fecha_foto=fecha_foto)
    return ev[ev["racha"] >= racha_minima].reset_index(drop=True)


def mascara_censura(filas, eventos):
    """True en las filas que se excluyen del entrenamiento: las del par de un evento cuyo origen es posterior o igual a la
    última venta y cuya ventana objetivo termina en o antes de la foto."""
    if eventos is None or len(eventos) == 0:
        return np.zeros(len(filas), dtype=bool)
    idx = filas[["codigo_item", "sucursal", "fecha_origen", "fin_ventana"]].reset_index().merge(
        eventos[["codigo_item", "sucursal", "ultima", "fecha_foto"]], on=["codigo_item", "sucursal"])
    dentro = (idx["fecha_origen"] >= idx["ultima"]) & (idx["fin_ventana"] <= idx["fecha_foto"])
    mascara = np.zeros(len(filas), dtype=bool)
    posiciones = pd.Index(filas.index).get_indexer(idx.loc[dentro, "index"].unique())
    mascara[posiciones] = True
    return mascara


# ── Estratos al corte ────────────────────────────────
def estratos_al_corte(volumen, cortes=(0.5, 0.8)):
    """Estrato por par a partir del volumen de los últimos 365 días hábiles (Series indexada por (codigo_item,
    sucursal)). Un par es cabeza si el volumen acumulado antes de él es menor que el 50 % del total, medio si es menor
    que el 80 % y cola si no; los pares sin volumen son cola."""
    v = volumen.sort_values(ascending=False, kind="stable")
    total = v.sum()
    previo = (v.cumsum() - v) / total if total > 0 else v * 0 + 1
    estrato = np.where(previo < cortes[0], "cabeza", np.where(previo < cortes[1], "medio", "cola"))
    estrato = np.where(v.to_numpy() <= 0, "cola", estrato)
    return dict(zip(v.index, estrato))


# ── Cortes walk-forward y reglas ─────────────────────
def cortes_walk_forward(fechas_origen, n_origenes=12, por_grupo=4):
    """Los últimos `n_origenes` orígenes en grupos de `por_grupo`: [(desde, hasta), ...]. Cada grupo se predice con un
    modelo entrenado con las ventanas que terminan antes de su primer origen."""
    fechas = sorted(pd.to_datetime(pd.Series(fechas_origen)).unique())
    if len(fechas) < n_origenes:
        raise ValueError(f"hacen falta {n_origenes} orígenes con la ventana completa y hay {len(fechas)}")
    ultimos = fechas[-n_origenes:]
    return [(pd.Timestamp(ultimos[i]), pd.Timestamp(ultimos[min(i + por_grupo, n_origenes) - 1]))
            for i in range(0, n_origenes, por_grupo)]


def regla_calendario(mejoras_altas, mejora_bajas, confirmacion_total):
    """Regla de `preregistro_receta_2026.json`: el calendario entra si baja el costo con intervalo por encima de 0 en
    cada temporada alta, no lo empeora en el resto del año (extremo alto ≥ 0) y, en todo junto, cumple los criterios de
    WAPE y cobertura (`confirmacion_total`, salida de `exploracion_2026.reglas_confirmacion`)."""
    altas = {k: bool(m["ic_bajo"] > 0) for k, m in mejoras_altas.items()}
    bajas = bool(mejora_bajas["ic_alto"] >= 0)
    wape_cobertura = bool(confirmacion_total["E2"] and confirmacion_total["E3"])
    entra = all(altas.values()) and bajas and wape_cobertura
    return dict(entra=entra, temporadas_altas=altas, resto_del_anio_no_peor=bajas, wape_y_cobertura=wape_cobertura)


# ── Versión de los datos ─────────────────────────────
def version_datos(ruta_fact_ventas):
    """(fecha máxima, huella de 12 caracteres) de `fact_ventas.csv`, sin cargarlo entero en memoria."""
    ruta = Path(ruta_fact_ventas)
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    fechas = pd.read_csv(ruta, usecols=["fecha"])["fecha"]
    return str(pd.to_datetime(fechas).max().date()), h.hexdigest()[:12]


def hay_datos_nuevos(version, ultima):
    """Hay datos nuevos si no hay corrida anterior terminada o si cambió la fecha máxima o la huella."""
    return ultima is None or tuple(version) != tuple(ultima)


# ── Calibración: fija, deslizante y adaptativa ───────
def _cuantil_conformal(residuos, nivel):
    n = len(residuos)
    return float(np.quantile(residuos, min(1.0, np.ceil((n + 1) * nivel) / n)))


def offsets_secuenciales(residuos_por_origen, offset_fijo, variante, nivel=NIVEL, ventana=VENTANA_DESLIZANTE,
                         gamma=GAMMA_ADAPTATIVA):
    """Ajuste de un estrato para cada origen, en orden, usando solo los orígenes anteriores (sus ventanas ya terminaron).
    `residuos_por_origen`: lista de arreglos de residuos relativos (y/base − cuantil sin ajuste) por origen.
    variante: 'fija' (siempre `offset_fijo`), 'deslizante' (cuantil conformal de los `ventana` orígenes anteriores) o
    'adaptativa' (como la deslizante, con el nivel corregido tras cada origen: nivel + gamma·(0,893 − cobertura))."""
    offsets, nivel_t = [], nivel
    for k, residuos in enumerate(residuos_por_origen):
        previos = residuos_por_origen[max(0, k - ventana):k]
        if variante == "fija" or not previos:
            off = offset_fijo
        else:
            off = _cuantil_conformal(np.concatenate(previos), nivel_t if variante == "adaptativa" else nivel)
        offsets.append(off)
        if variante == "adaptativa" and len(residuos):
            cobertura = float((np.asarray(residuos) <= off).mean())
            nivel_t = float(np.clip(nivel_t + gamma * (nivel - cobertura), 0.5, 0.999))
    return offsets


# ── Orquestación de una corrida ──────────────────────
class MlflowNoResponde(RuntimeError):
    """MLflow no responde: la corrida falla de forma visible (código 2) sin entrenar."""


def orquestar(ops):
    """Flujo de una corrida programada (sección 4 de docs/INV-62-requerimientos.md). `ops` implementa:
    mlflow_ok() → bool; version() → (fecha, huella); ultima_version() → (fecha, huella) o None;
    evaluar() → dict con 'cumple' y el detalle de la regla de promoción; exportar(evaluacion) → nombre de la rama;
    registrar(estado, info) → id del run. Si algo falla después de la compuerta, se registra 'fallo' y se relanza el error."""
    if not ops.mlflow_ok():
        raise MlflowNoResponde("MLflow no responde: no se entrena")
    version = ops.version()
    if not hay_datos_nuevos(version, ops.ultima_version()):
        return dict(estado="sin_datos_nuevos", version=version, run_id=ops.registrar("sin_datos_nuevos", dict(version=version)))
    try:
        evaluacion = ops.evaluar()
        if not evaluacion["cumple"]:
            info = dict(version=version, evaluacion=evaluacion)
            return dict(estado="rechazado", version=version, evaluacion=evaluacion, run_id=ops.registrar("rechazado", info))
        rama = ops.exportar(evaluacion)
        info = dict(version=version, evaluacion=evaluacion, rama=rama)
        return dict(estado="promovible", version=version, evaluacion=evaluacion, rama=rama, run_id=ops.registrar("promovible", info))
    except Exception as error:
        ops.registrar("fallo", dict(version=version, error=f"{type(error).__name__}: {error}"))
        raise
