"""
INV-63 — Funciones del holdout 2026: orígenes, universo, reglas R1 a R4 y
veredicto, tal como las fija el preregistro (`preregistro_holdout_2026.json`,
explicado en `docs/PREREGISTRO-HOLDOUT-2026.md`).

Son funciones puras: reciben tablas y resultados ya calculados y devuelven
decisiones. El orquestador (`16_holdout_2026.py`) arma los datos, predice con
el motor congelado, calcula las métricas con `evaluar_nivel1.py` y registra en
MLflow. Así cada regla se prueba con datos sintéticos
(`notebooks/tests/test_holdout_2026.py`) sin tocar datos del negocio.

Desviación D1 (17-nov): el universo principal son los pares del paquete
congelado cuyo producto está en las fotos de inventario de dic-2025 y sep-2026;
el universo preregistrado (v1) se reporta como sensibilidad, sin decisión.
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONTE = 15                  # días hábiles de la ventana objetivo
MINIMO_ORIGENES = 8             # con menos, el resultado es un indicio y no activa acciones
TOLERANCIA_COBERTURA = 0.05     # R3: |cobertura - alpha| máxima
MINIMO_FILAS_ESTRATO = 200      # R3 y R4: estratos con menos filas no deciden ('insuficiente')
ALPHA_NO_PERECEDERO = 0.893     # R4 compara la cobertura contra este alpha


def origenes_holdout(fechas_habiles, inicio="2026-01-01", horizonte=HORIZONTE):
    """Rejilla mecánica del preregistro: el primer día hábil desde `inicio` y luego cada
    `horizonte` días hábiles, mientras la ventana objetivo (t+1 .. t+horizonte) esté completa.
    Un día hábil es un día con alguna venta en el negocio (`calendario_habil.csv` de 01)."""
    fechas = pd.DatetimeIndex(sorted(pd.DatetimeIndex(fechas_habiles)))
    i0 = int(np.searchsorted(fechas.values, np.datetime64(pd.Timestamp(inicio))))
    ultimo = len(fechas) - 1
    return pd.DatetimeIndex([fechas[i] for i in range(i0, len(fechas), horizonte) if i + horizonte <= ultimo])


def estado_resultado(n_origenes, minimo=MINIMO_ORIGENES):
    """'veredicto' con al menos `minimo` orígenes; si no, 'indicio' (se reporta y no activa acciones)."""
    return "veredicto" if n_origenes >= minimo else "indicio"


def universo_d1(filas, productos_en_inventarios):
    """Desviación D1: solo los pares cuyo producto está en todas las fotos de inventario dadas."""
    return filas[filas["codigo_item"].astype(str).isin(set(map(str, productos_en_inventarios)))]


def regla_r1(mejora_wape):
    """R1 (intermitente): mejora del WAPE del q50 frente a la media móvil, con IC95 > 0.
    `mejora_wape` es la salida de `evaluar_nivel1.mejora_con_ic`."""
    cumple = bool(mejora_wape["ic_bajo"] > 0)
    return dict(regla="R1", cumple=cumple, estado="confirmada" if cumple else "no_confirmada",
                accion=None if cumple else "se reevalua en el reentrenamiento (INV-62)",
                mejora_rel=mejora_wape["mejora_rel"], ic_bajo=mejora_wape["ic_bajo"], ic_alto=mejora_wape["ic_alto"])


def regla_r2(mejora_costo):
    """R2 (intermitente): mejora del costo Cu/Co del cuantil de negocio frente a la referencia
    `baseline_cuantil` congelada. IC > 0 se mantiene; IC que cruza 0 se mantiene sin confirmar;
    IC entero < 0 cambia la rama a `baseline_cuantil`. Salida de `mejora_perdida_con_ic`."""
    if mejora_costo["ic_bajo"] > 0:
        estado, accion = "confirmada", None
    elif mejora_costo["ic_alto"] < 0:
        estado, accion = "no_cumple", "la rama intermitente pasa a baseline_cuantil con la referencia congelada"
    else:
        estado, accion = "ic_cruza_cero", None
    return dict(regla="R2", cumple=estado != "no_cumple", estado=estado, accion=accion,
                mejora_rel=mejora_costo["mejora_rel"], ic_bajo=mejora_costo["ic_bajo"], ic_alto=mejora_costo["ic_alto"])


def regla_r3(coberturas):
    """R3 (las tres ramas): |cobertura - alpha| <= 0,05 en cada rama completa y en cada estrato con al
    menos 200 filas. `coberturas` es una tabla con rama, estrato (None = la rama completa), n_filas,
    cobertura y alpha. Si una rama falla, se reestiman sus offsets (intermitente) o razones (suaves)."""
    tabla = pd.DataFrame(coberturas).copy()
    es_rama = tabla["estrato"].isna()
    tabla["evaluable"] = es_rama | (tabla["n_filas"] >= MINIMO_FILAS_ESTRATO)
    tabla["desvio"] = (tabla["cobertura"] - tabla["alpha"]).abs()
    tabla["resultado"] = np.where(~tabla["evaluable"], "insuficiente",
                                  np.where(tabla["desvio"] <= TOLERANCIA_COBERTURA, "cumple", "no_cumple"))
    fallan = sorted(tabla.loc[tabla["resultado"] == "no_cumple", "rama"].unique())
    acciones = [f"reestimar {'offsets' if r == 'intermitente' else 'razones'} de la rama {r} con 2026, sin tocar el modelo"
                for r in fallan]
    return dict(regla="R3", cumple=not fallan, estado="confirmada" if not fallan else "no_cumple",
                ramas_que_fallan=fallan, accion="; ".join(acciones) or None, detalle=tabla)


def regla_r4(por_estrato, mejora_costo_cal_vs_sin):
    """R4 (intermitente): la calibración por estrato frente a la misma predicción sin offset.
    Cumple si la cobertura queda más cerca de 0,893 en al menos 2 de los estratos evaluables
    (≥ 200 filas) y el costo no es peor (ic_alto de la mejora cal vs sin_cal >= 0)."""
    tabla = pd.DataFrame(por_estrato).copy()
    tabla = tabla[tabla["n_filas"] >= MINIMO_FILAS_ESTRATO]
    tabla["mas_cerca"] = ((tabla["cobertura_cal"] - ALPHA_NO_PERECEDERO).abs()
                          < (tabla["cobertura_sin_cal"] - ALPHA_NO_PERECEDERO).abs())
    n_mas_cerca = int(tabla["mas_cerca"].sum())
    costo_no_peor = bool(mejora_costo_cal_vs_sin["ic_alto"] >= 0)
    cumple = n_mas_cerca >= 2 and costo_no_peor
    return dict(regla="R4", cumple=cumple, estado="confirmada" if cumple else "no_cumple",
                accion=None if cumple else "se desactiva la calibracion por estrato (equivale a --sin-calibracion)",
                estratos_evaluables=int(len(tabla)), estratos_mas_cerca=n_mas_cerca, costo_no_peor=costo_no_peor,
                mejora_costo_rel=mejora_costo_cal_vs_sin["mejora_rel"], ic_bajo=mejora_costo_cal_vs_sin["ic_bajo"],
                ic_alto=mejora_costo_cal_vs_sin["ic_alto"])


def veredicto_global(reglas, estado):
    """'politica_confirmada' si R1 a R4 se cumplen; si no, las acciones de las reglas que fallan.
    R1 y R2 «no confirmadas» no cambian la política. Con 'indicio' no se activa ninguna acción."""
    if estado == "indicio":
        return dict(veredicto="indicio", acciones=[])
    acciones = [f"{r['regla']}: {r['accion']}" for r in reglas if r.get("accion")]
    confirmada = all(r["estado"] == "confirmada" for r in reglas)
    return dict(veredicto="politica_confirmada" if confirmada else ("con_acciones" if acciones else "se_mantiene_sin_confirmar"),
                acciones=acciones)


def huella_filas(matriz, hasta, claves=("codigo_item", "sucursal", "fecha_origen")):
    """Huella de las filas de la matriz con fecha_origen <= `hasta`, independiente del orden de las
    filas: la compuerta de identidad del preregistro compara la matriz re-ejecutada con la congelada
    sin trasladar el archivo. Devuelve (n_filas, sha256 de 12 caracteres)."""
    sub = matriz[pd.to_datetime(matriz["fecha_origen"]) <= pd.Timestamp(hasta)]
    sub = sub.sort_values(list(claves), kind="mergesort").reset_index(drop=True)
    sub = sub[sorted(sub.columns)]
    filas = pd.util.hash_pandas_object(sub, index=False).to_numpy()
    return len(sub), hashlib.sha256(filas.tobytes()).hexdigest()[:12]


def verificar_huellas(archivos_sha256, raiz):
    """Compara el SHA-256 completo de cada archivo con el del preregistro. Devuelve la lista de
    archivos que no coinciden (vacía si todo está bien); el orquestador falla si no está vacía."""
    distintos = []
    for rel, esperado in archivos_sha256.items():
        ruta = Path(raiz) / rel
        h = hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else None
        if h != esperado:
            distintos.append(rel)
    return distintos
