"""
INV-63 — Funciones de la exploración preregistrada de features y algoritmos
(`preregistro_exploracion_2026.json`, H10 a H12 de docs/INV-63-requerimientos.md).

Funciones puras sobre matrices de venta diaria (días hábiles × pares, con 0 en
los días hábiles sin venta, la misma rejilla que `features.py`): las features
nuevas de C1 y C2, la rejilla y las particiones con purge, y las reglas de
selección y de confirmación. El orquestador (`17_exploracion_2026.py`) arma
los datos, entrena y registra en MLflow. Pruebas con datos sintéticos en
`notebooks/tests/test_exploracion_2026.py` (P11).
"""
import numpy as np
import pandas as pd

HORIZONTE = 15
ALPHA = 0.893
TOLERANCIA_COBERTURA = 0.05
MINIMO_FILAS_ESTRATO = 200
MARCAS_VENTANA = {          # feature -> columna booleana de dim_tiempo
    "frac_festivo": "es_festivo",
    "frac_puente": "es_puente_festivo",
    "frac_quincena": "es_quincena",
    "frac_fin_semana": "es_fin_semana",
    "frac_semana_santa": "es_semana_santa",
    "frac_prima": "es_periodo_prima",
}
FEATURES_C1 = [*MARCAS_VENTANA, "frac_bloque_dic", "mes_origen", "dias_naturales_ventana", "venta_aa", "razon_aa"]
FEATURES_C2 = ["sba_15", "tsb_15", "ewm_15", "trail_60", "frac_ceros_60", "edad_habiles"]


# ── Rejilla y particiones ────────────────────────────
def rejilla(fechas_habiles, ancla="2026-01-02", hasta="2026-09-15", horizonte=HORIZONTE):
    """Índices de los orígenes cada `horizonte` días hábiles anclados en `ancla`, hacia atrás hasta el
    inicio y hacia adelante hasta `hasta`, solo si la ventana t+1..t+horizonte está completa."""
    fechas = pd.DatetimeIndex(fechas_habiles)
    a = fechas.get_loc(pd.Timestamp(ancla))
    ultimo = len(fechas) - 1
    idx = range(a % horizonte, len(fechas), horizonte)
    return np.array([i for i in idx if i + horizonte <= ultimo and fechas[i] <= pd.Timestamp(hasta)])


def particion(fecha_origen, fin_ventana, desde, hasta):
    """(entrenamiento, prueba) como máscaras booleanas. Prueba: orígenes en [desde, hasta]. Entrenamiento:
    filas cuya ventana objetivo termina en o antes del primer origen de prueba (purge)."""
    fecha_origen, fin_ventana = pd.to_datetime(pd.Series(fecha_origen)), pd.to_datetime(pd.Series(fin_ventana))
    prueba = (fecha_origen >= pd.Timestamp(desde)) & (fecha_origen <= pd.Timestamp(hasta))
    if not prueba.any():
        return (prueba & False).to_numpy(), prueba.to_numpy()
    inicio = fecha_origen[prueba].min()
    entrenamiento = (fin_ventana <= inicio) & (fecha_origen < inicio)
    return entrenamiento.to_numpy(), prueba.to_numpy()


# ── Features de C2: demanda intermitente ─────────────
def croston_sba(x, alfa=0.1):
    """Croston con la corrección de Syntetos-Boylan, por columna, con la información hasta cada día inclusive.
    Tamaño z e intervalo p se inician con la primera venta (p = días hasta ella). NaN antes de la primera venta."""
    x = np.asarray(x, dtype=float)
    t_dias, n = x.shape
    z = np.full(n, np.nan)
    p = np.full(n, np.nan)
    q = np.zeros(n)
    salida = np.full((t_dias, n), np.nan)
    for t in range(t_dias):
        q += 1
        venta = x[t] > 0
        nueva = venta & np.isnan(z)
        z[nueva], p[nueva] = x[t][nueva], q[nueva]
        sigue = venta & ~nueva
        z[sigue] += alfa * (x[t][sigue] - z[sigue])
        p[sigue] += alfa * (q[sigue] - p[sigue])
        q[venta] = 0
        salida[t] = (1 - alfa / 2) * z / p
    return salida


def tsb(x, alfa=0.1, beta=0.1):
    """Teunter-Syntetos-Babai, por columna: probabilidad de venta y tamaño se actualizan cada día (la
    probabilidad decae en los días sin venta). Se inicia en la primera venta con probabilidad
    1 / (días hasta ella) y tamaño igual a esa venta. Devuelve la demanda esperada por día; NaN antes."""
    x = np.asarray(x, dtype=float)
    t_dias, n = x.shape
    z = np.full(n, np.nan)
    p = np.full(n, np.nan)
    salida = np.full((t_dias, n), np.nan)
    for t in range(t_dias):
        venta = x[t] > 0
        nueva = venta & np.isnan(z)
        z[nueva], p[nueva] = x[t][nueva], 1.0 / (t + 1)
        iniciada = ~np.isnan(z) & ~nueva
        p[iniciada] += beta * (venta[iniciada].astype(float) - p[iniciada])
        con_venta = iniciada & venta
        z[con_venta] += alfa * (x[t][con_venta] - z[con_venta])
        salida[t] = p * z
    return salida


def ewm(x, span=HORIZONTE):
    """Media exponencial por columna (alfa = 2 / (span + 1)), iniciada en el primer día."""
    x = np.asarray(x, dtype=float)
    a = 2.0 / (span + 1)
    salida = np.empty_like(x)
    salida[0] = x[0]
    for t in range(1, len(x)):
        salida[t] = salida[t - 1] + a * (x[t] - salida[t - 1])
    return salida


def features_c2(x, i, sba, tsb_, ewm_, horizonte=HORIZONTE):
    """Features de C2 de todos los pares en el día hábil `i` (origen), con las recursiones ya calculadas."""
    x = np.asarray(x, dtype=float)
    ventana = x[max(0, i - 59):i + 1]
    con_venta = x[:i + 1] > 0
    primera = np.where(con_venta.any(axis=0), con_venta.argmax(axis=0), -1)
    return {
        "sba_15": sba[i] * horizonte,
        "tsb_15": tsb_[i] * horizonte,
        "ewm_15": ewm_[i] * horizonte,
        "trail_60": ventana.sum(axis=0),
        "frac_ceros_60": (ventana == 0).mean(axis=0),
        "edad_habiles": np.where(primera >= 0, i - primera, np.nan).astype(float),
    }


# ── Features de C1: calendario y estacionalidad ──────
def marcas_ventana(marcas, dias_ventana):
    """Fracción de los días hábiles de la ventana objetivo con cada marca de dim_tiempo."""
    m = marcas.reindex(pd.DatetimeIndex(dias_ventana))
    salida = {f: float(m[c].astype(bool).mean()) for f, c in MARCAS_VENTANA.items()}
    salida["frac_bloque_dic"] = float((m["bloque_diciembre"].fillna("ninguno") != "ninguno").mean())
    return salida


def venta_anio_anterior(acumulada, fechas_habiles, inicio, fin, desfase_dias=364):
    """Venta de cada par en las fechas [inicio - desfase, fin - desfase] (mismos días de la semana un año antes).
    `acumulada` es la suma acumulada por columna de la matriz de venta diaria sobre `fechas_habiles`;
    los días sin venta no están en la rejilla, así que sumar sus días hábiles es sumar las fechas."""
    fechas = pd.DatetimeIndex(fechas_habiles)
    a = int(np.searchsorted(fechas.values, np.datetime64(pd.Timestamp(inicio) - pd.Timedelta(days=desfase_dias))))
    b = int(np.searchsorted(fechas.values, np.datetime64(pd.Timestamp(fin) - pd.Timedelta(days=desfase_dias)), side="right"))
    if b <= a:
        return np.zeros(acumulada.shape[1])
    return acumulada[b - 1] - (acumulada[a - 1] if a > 0 else 0.0)


def trail_anio_anterior(acumulada, fechas_habiles, origen, horizonte=HORIZONTE, desfase_dias=364):
    """Venta de los `horizonte` días hábiles que terminan en el último día hábil <= origen - desfase."""
    fechas = pd.DatetimeIndex(fechas_habiles)
    j = int(np.searchsorted(fechas.values, np.datetime64(pd.Timestamp(origen) - pd.Timedelta(days=desfase_dias)), side="right")) - 1
    if j < horizonte - 1:
        return np.full(acumulada.shape[1], np.nan)
    return acumulada[j] - (acumulada[j - horizonte] if j - horizonte >= 0 else 0.0)


# ── Reglas ───────────────────────────────────────────
def regla_seleccion(comparaciones):
    """Elige el candidato según el preregistro. `comparaciones`: una fila por candidato distinto de C0 con
    id, costo, costo_ic_bajo (mejora de costo frente a C0), wape_ic_alto (mejora de WAPE frente a C0) y
    cobertura. Gana el de menor costo entre los que cumplen las tres condiciones; si ninguno, C0."""
    t = pd.DataFrame(comparaciones).copy()
    t["cumple_costo"] = t["costo_ic_bajo"] > 0
    t["cumple_wape"] = t["wape_ic_alto"] >= 0
    t["cumple_cobertura"] = (t["cobertura"] - ALPHA).abs() <= TOLERANCIA_COBERTURA
    t["elegible"] = t["cumple_costo"] & t["cumple_wape"] & t["cumple_cobertura"]
    elegibles = t[t["elegible"]]
    elegido = "C0" if elegibles.empty else str(elegibles.sort_values("costo").iloc[0]["id"])
    return elegido, t


def reglas_confirmacion(mejora_costo, mejora_wape, coberturas):
    """E1 (costo frente al congelado, IC95 > 0), E2 (WAPE no peor, ic_alto >= 0) y E3 (cobertura a ±0,05 de
    0,893 en la rama y en los estratos con ≥ 200 filas). `coberturas`: filas con estrato (None = rama), n_filas
    y cobertura."""
    tabla = pd.DataFrame(coberturas).copy()
    tabla["evaluable"] = tabla["estrato"].isna() | (tabla["n_filas"] >= MINIMO_FILAS_ESTRATO)
    tabla["cumple"] = ~tabla["evaluable"] | ((tabla["cobertura"] - ALPHA).abs() <= TOLERANCIA_COBERTURA)
    e1 = bool(mejora_costo["ic_bajo"] > 0)
    e2 = bool(mejora_wape["ic_alto"] >= 0)
    e3 = bool(tabla["cumple"].all())
    return dict(E1=e1, E2=e2, E3=e3, cumple=e1 and e2 and e3, detalle_e3=tabla,
                mejora_costo=mejora_costo["mejora_rel"], costo_ic=(mejora_costo["ic_bajo"], mejora_costo["ic_alto"]),
                mejora_wape=mejora_wape["mejora_rel"], wape_ic=(mejora_wape["ic_bajo"], mejora_wape["ic_alto"]))
