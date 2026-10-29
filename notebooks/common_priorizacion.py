"""
Módulo compartido de la cadena de notebooks de priorización de SKU para
desabastecimiento (01_calidad_y_panel -> 05_sintesis).

Contiene únicamente PARAMS, rutas, y funciones PURAS reutilizadas por varios
notebooks -- ningún notebook debe recalcular lo que otro ya produjo como CSV;
en cambio importa de aquí la lógica compartida para no duplicar el criterio.

No se ejecuta como script; se importa con:
    import sys; sys.path.insert(0, '.')
    from common_priorizacion import PARAMS, DW, hash_archivo, ...
"""
from pathlib import Path
import hashlib
import json
import re
import unicodedata

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
# INV-14 -- adaptado de ventas2/common_priorizacion.py (BASE_DIR/"dw"/"salida"
# ahí): en InventaIO el DW real lo produce etl_real/, pero su salida
# (etl_real/config.py::SALIDA_DIR) vive en <raíz del repo>/data/processed_real,
# no bajo etl_real/ -- BASE_DIR.parent es la raíz del repo (padre de notebooks/).
DW = BASE_DIR.parent / "data" / "processed_real"

# ── Parámetros de la regla de negocio y del EDA, con origen documentado ──
PARAMS = {
    # -- dados por el negocio --
    "UMBRAL_VOLUMEN_CM3": 3000,          # condición 1
    "UMBRAL_PESO_G": 3000,                # condición 1
    "UMBRAL_ROLLOS_PAPEL_HIGIENICO": 18,  # condición 4 (ajustado: 24 -> 18)
    "TOP_N_SUCURSAL": 50,                 # condición 6

    # -- decididos en el EDA (no especificados por el negocio) --
    "MIN_DIAS_VENTANA": 180,
    "UMBRAL_FRECUENCIA_COND7": 0.98,
    "UMBRAL_NUMERO_SUELTO_INFERENCIA": 50,
    "ADI_CORTE": 1.32,
    "CV2_CORTE": 0.49,
    "UMBRAL_FRECUENCIA_RACHA_CONTROL": 0.5,
    "HORIZONTE_BASELINE_DIAS": 15,
    "MIN_DIAS_TRAIN_BASELINE": 60,
    "VENTANA_ACTIVIDAD_BASELINE_DIAS": 90,  # días hábiles sin vender antes del origen para considerar un par "vivo" (04, A2 de su revisión)
    "VENTANA_ESTACIONAL_DIAS": 7,
    "ORIGENES_BASELINE": {
        "ordinario_1": "2024-06-01", "ordinario_2": "2025-02-01",
        "semana_santa": "2024-03-25", "diciembre_alto": "2024-12-01",
    },
    "UMBRAL_FALSO_POSITIVO_TEMPORADA": 0.15,
    "UMBRAL_FALSO_NEGATIVO_TEMPORADA": 0.40,
    "DICIEMBRE_NOVENA": (16, 23),
    "DICIEMBRE_NOCHEBUENA_NAVIDAD": (24, 25),
    "DICIEMBRE_FIN_DE_ANIO": (30, 31),
    "ENERO_POSTNAVIDAD_MAX_DIA": 6,
    "PERIODO_PRIMA_JUNIO": (10, 30),
    "PERIODO_PRIMA_DICIEMBRE": (1, 20),
    "UMBRAL_INCLUSION_EFECTO_CALENDARIO": 0.05,  # |controlado_x - 1| >= esto para "incluir" (sección 05)

    # -- decisión de datos, tomada en 01_calidad_y_panel (A2 de su revisión) --
    # ACTUALIZADO (INV-61, ventas2): el negocio trajo los reportes que
    # faltaban de marzo-abril y noviembre-diciembre 2023 ("marz abril
    # 2023.xlsx", "nov dic 2023.xlsx") -- eso cerró por completo los
    # bloques de 2023-11 y 2023-12 (0 días de residuo tras la re-ejecución
    # de parse_ventas_dir.py en ventas2, ver docs/INV-61-inventario-real.md
    # de este repo). Queda un
    # único bloque grande: 2023-02 (23 días, 2 a 21 de febrero), que sigue
    # siendo un hueco genuino dentro de "en fe 2023.xlsx" (no un archivo
    # faltante) -- no hay reporte de origen para llenarlo.
    # ACTUALIZADO OTRA VEZ (fix datos-2022, sin ticket): se sumó el
    # histórico de 2022 (enero-octubre, 5 xlsx nuevos en ventas2), pero
    # el negocio NO trajo noviembre-diciembre 2022 -- a diferencia del
    # hueco de 2023-02 (23 días dentro de un archivo), este es un bloque
    # de 2 MESES COMPLETOS sin ningún reporte de origen (confirmado:
    # fact_ventas.csv no tiene una sola fila en 2022-11/2022-12, aunque
    # dim_tiempo.csv sí cubre esas fechas por ser parte del rango
    # min-max). Se renombra el parámetro de MESES_2023_INCOMPLETOS a
    # MESES_INCOMPLETOS (ya no aplica solo a 2023) -- actualizar las
    # referencias en 01/03/05 si se vuelve a renombrar.
    # Decisión: NO se trunca el histórico -- se conserva todo lo demás
    # porque son datos reales y útiles para la regla de priorización y
    # los patrones de demanda, que no dependen de comparar años
    # completos. `huecos_globales_set`/`fechas_habiles` ya excluyen estos
    # días de todo cálculo de días hábiles/frecuencia en toda la cadena.
    # Lo que SÍ queda contaminado es cualquier comparación o
    # entrenamiento que asuma un año completo como referencia (p.ej. un
    # leave-one-year-out anual, o el término de Fourier anual si el hueco
    # cae en una fase relevante) -- los notebooks 03/05 deben excluir
    # estos meses de cualquier promedio "por año" o comparación
    # interanual completa.
    "MESES_INCOMPLETOS": ["2022-11", "2022-12", "2023-02"],
}


def hash_archivo(path):
    """SHA-256 (12 chars) de un archivo -- huella de reproducibilidad. None si no existe."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except FileNotFoundError:
        return None


def registrar_huella(nombres_archivos, base_dir=DW):
    return {n: hash_archivo(Path(base_dir) / n) for n in nombres_archivos}


def dias_habiles_en_ventana(primera, ultima, huecos_globales_set):
    """Días de calendario entre primera y ultima (inclusive), menos los que
    son huecos globales (sin ninguna venta en todo el negocio)."""
    total = (ultima - primera).days + 1
    huecos_en_ventana = sum(1 for f in huecos_globales_set if primera <= f <= ultima)
    return total - huecos_en_ventana


def construir_df_razon(serie_zero_filled, ventana_dias=None):
    """DataFrame diario con la razón de cada día sobre su propia media móvil
    centrada -- base del índice de día de semana (indice_dia_semana)."""
    ventana_dias = ventana_dias or PARAMS["VENTANA_ESTACIONAL_DIAS"]
    df = pd.DataFrame({"valor": serie_zero_filled.values}, index=serie_zero_filled.index)
    df["dia_semana"] = df.index.map(lambda f: f.isoweekday())
    df["mm"] = df["valor"].rolling(ventana_dias, min_periods=max(2, ventana_dias // 2), center=True).mean()
    df["razon"] = df["valor"] / df["mm"]
    return df


def indice_dia_semana(df_razon):
    return df_razon.groupby("dia_semana")["razon"].median()


def normalizar_nombre(n):
    """Mayúsculas, sin tildes, solo alfanumérico y espacios simples --
    usado para comparar nombres de producto entre esquemas de código (01) y
    en el parseo de las condiciones de la regla de negocio (02)."""
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    n = re.sub(r"[^A-Z0-9 ]", " ", n.upper())
    return re.sub(r"\s+", " ", n).strip()


def cargar_dw(nombre, **kwargs):
    """Atajo para pd.read_csv sobre dw/salida/<nombre>."""
    return pd.read_csv(DW / nombre, **kwargs)


# ── Lectores de los artefactos de la cadena (A1 de la revisión de 01) ──
# Ningún notebook debe hacer pd.read_csv/read_parquet directo sobre una
# salida de otro notebook -- pasa por aquí, así el dtype/parse_dates es una
# sola definición y un CSV mal tipado (p.ej. codigo_item inferido como int64,
# que rompe el join contra dim_producto EN SILENCIO) no puede ocurrir dos
# veces distinto.

def leer_panel():
    """panel_diario.parquet -- codigo_item, sucursal, fecha, unidades, valor
    (sucursales reales, ventas netas). Producido por 01."""
    return pd.read_parquet(DW / "panel_diario.parquet")


def leer_panel_negocio():
    """panel_diario_negocio.parquet -- codigo_item, fecha, cantidad (incluye
    SIN_SUCURSAL). Producido por 01."""
    return pd.read_parquet(DW / "panel_diario_negocio.parquet")


def leer_ventana():
    """ventana_activa.parquet -- ventana activa por par producto x sucursal
    (sucursales reales). Producido por 01."""
    return pd.read_parquet(DW / "ventana_activa.parquet")


def leer_ventana_negocio():
    """ventana_activa_negocio.parquet -- ventana activa por producto a nivel
    negocio (incluye SIN_SUCURSAL) -- la usa la condición 7 en 02. Producido por 01."""
    return pd.read_parquet(DW / "ventana_activa_negocio.parquet")


def leer_huecos():
    """huecos_calendario.csv -- fechas sin ninguna venta en todo el negocio.
    Devuelve (lista ordenada, set) listo para dias_habiles_en_ventana. Producido por 01."""
    df = pd.read_csv(DW / "huecos_calendario.csv", parse_dates=["fecha"])
    huecos = sorted(df["fecha"])
    return huecos, set(huecos)


def leer_priorizacion():
    """priorizacion_producto_sucursal.parquet -- flags de las 7 condiciones y
    es_prioritario, al grano producto x sucursal. Producido por 02."""
    return pd.read_parquet(DW / "priorizacion_producto_sucursal.parquet")


def leer_dim_priorizado():
    """dim_producto_priorizado.parquet -- dim_producto con las columnas de
    parseo (volumen_cm3, peso_g, rollos_paquete...) y las 7 condiciones a
    nivel producto. Producido por 02."""
    return pd.read_parquet(DW / "dim_producto_priorizado.parquet")


def leer_efectos_calendario():
    """efectos_calendario.csv -- efecto parcial (controlado_x), IC 95%,
    n_anios_evidencia y bandera sensible_a_especificacion por evento de
    calendario. Producido por 03; 05 lee esto EN CÓDIGO para decidir features."""
    return pd.read_csv(DW / "efectos_calendario.csv")


def leer_calendario_eventos():
    """calendario_eventos.csv -- fecha a fecha, con festivo/víspera/resaca/
    puente/Semana Santa/bloque de diciembre/período de prima/navidad.
    Producido por 03."""
    return pd.read_csv(DW / "calendario_eventos.csv", parse_dates=["fecha"])


def leer_estacionalidad_sku():
    """estacionalidad_sku.parquet -- ratio de concentración en navidad y
    Semana Santa por producto, con la marca de la condición 5. Producido por 03."""
    return pd.read_parquet(DW / "estacionalidad_sku.parquet")


def leer_indices_categoria_sucursal():
    """estacionalidad_indices_categoria_sucursal.csv -- índice de día de
    semana por categoría x sucursal, para las categorías que concentran las
    condiciones 1-5. Producido por 03."""
    return pd.read_csv(DW / "estacionalidad_indices_categoria_sucursal.csv")


def leer_calendario_habil():
    """calendario_habil.csv -- fecha -> índice de día hábil (posición dentro
    del calendario sin huecos globales). Devuelve (DatetimeIndex, pd.Series
    fecha->índice), igual forma que fechas_habiles/indice_habil en 01. Producido por 01."""
    df = pd.read_csv(DW / "calendario_habil.csv", parse_dates=["fecha"])
    fechas_habiles = pd.DatetimeIndex(df["fecha"])
    indice_habil = pd.Series(df["indice_habil"].values, index=fechas_habiles)
    return fechas_habiles, indice_habil


def fin_ventana_de(df, horizonte=15):
    """Fecha en que termina la ventana objetivo (t+1..t+H días hábiles) de cada fila de una
    matriz as-of. Se usa para purgar el entrenamiento (ver `purgar_entrenamiento`)."""
    fechas_habiles, indice_habil = leer_calendario_habil()
    i = df["fecha_origen"].map(indice_habil).to_numpy().astype(int)
    return pd.DatetimeIndex(fechas_habiles[np.minimum(i + horizonte, len(fechas_habiles) - 1)])


def inicio_test_de_fold(fold_id, horizonte=15):
    """Primer día de test de un fold, leído de la huella de 07 (única fuente de los FOLDS)."""
    sufijo = "" if horizonte == 15 else f"_h{horizonte}"
    with open(DW / f"huella_07{sufijo}.json") as f:
        folds = json.load(f)["parametros"]["folds"]
    for fold in folds:
        if fold["fold_id"] == fold_id:
            return pd.Timestamp(fold["test_start"])
    raise KeyError(f"fold {fold_id} no está en huella_07{sufijo}.json")


def purgar_entrenamiento(matriz, fold_id, horizonte=15, verbose=True):
    """Filas de entrenamiento válidas para evaluar `fold_id`: las de folds anteriores cuya ventana
    objetivo termina ANTES del primer día de test de ese fold.

    Los folds de 07 son adyacentes (el test de un fold termina el día antes de que empiece el
    siguiente) y la ventana objetivo dura H días hábiles: sin este descarte, las últimas filas de
    entrenamiento contienen como etiqueta demanda que ocurre dentro del periodo de prueba, y el
    modelo la "ha visto" al predecirla (purge estándar en validación walk-forward con etiquetas
    a horizonte). Con h=15 descarta ~20% del entrenamiento del fold 2 y 3-6% en los demás."""
    previas = matriz[matriz["fold_id"] < fold_id]
    fin = previas["fin_ventana"] if "fin_ventana" in previas.columns else pd.Series(
        fin_ventana_de(previas, horizonte), index=previas.index)
    ok = fin < inicio_test_de_fold(fold_id, horizonte)
    if verbose:
        print(f"  purge fold {fold_id}: {int((~ok).sum()):,} de {len(previas):,} filas de entrenamiento "
              f"({(~ok).mean():.1%}) descartadas por ventana solapada con el test")
    return previas[ok]


def leer_patron_demanda():
    """patron_demanda_producto_sucursal.parquet -- ADI/CV2 diario y semanal,
    patrón de demanda, por par producto x sucursal. Producido por 04."""
    return pd.read_parquet(DW / "patron_demanda_producto_sucursal.parquet")


def leer_baseline_wape():
    """baseline_wape.parquet -- errores del baseline de 3 métodos, por par y
    origen de pronóstico. Producido por 04."""
    return pd.read_parquet(DW / "baseline_wape.parquet")


def leer_racha_por_par():
    """racha_por_par.parquet -- racha máxima de ceros por par (TODOS los
    pares, no solo alta frecuencia), con frecuencia_venta, es_prioritario y
    grupo_condicion (solo_1_a_5/solo_6_o_7/ambas/no_prioritario) ya
    resueltos. Producido por 04 (B2 de la revisión de 05)."""
    return pd.read_parquet(DW / "racha_por_par.parquet")


def leer_diagnostico_features_riesgo():
    """diagnostico_features_riesgo.json -- demanda con/sin proxy de
    descuento y % de devoluciones en perecederos/refrigerados vs. catálogo.
    Producido por 04 (C3 de la revisión de 05, evita recalcular en 05 lo
    que 04 ya midió)."""
    import json
    return json.loads((DW / "diagnostico_features_riesgo.json").read_text())


def verificar_huella(nombre_json, archivos_a_verificar, base_dir=DW):
    """Compara el hash actual de `archivos_a_verificar` (rutas relativas a
    base_dir) contra lo registrado en <base_dir>/<nombre_json>['salidas'] (o
    ['entradas'] si no hay 'salidas'). Imprime advertencia si no coincide --
    no lanza excepción, para no bloquear una ejecución exploratoria (B3)."""
    import json
    path_json = Path(base_dir) / nombre_json
    if not path_json.exists():
        print(f'AVISO: no existe {path_json} -- no se puede verificar huella de entrada.')
        return
    registrado = json.loads(path_json.read_text())
    huella_registrada = registrado.get("salidas", registrado.get("entradas", {}))
    ok = True
    for nombre in archivos_a_verificar:
        actual = hash_archivo(Path(base_dir) / nombre)
        esperado = huella_registrada.get(nombre)
        if esperado is None:
            print(f'AVISO: {nombre} no está en la huella de {nombre_json}.')
            ok = False
        elif actual != esperado:
            print(f'AVISO: {nombre} cambió desde que {nombre_json} se generó (hash {esperado} -> {actual}) -- reejecutar la cadena desde ahí.')
            ok = False
    if ok:
        print(f'Huella verificada OK contra {nombre_json}.')


def estratos_as_of(fecha_corte, ventana=365, cortes=(0.5, 0.8)):
    """Estrato de volumen de cada par (codigo_item, sucursal), usando SOLO datos hasta `fecha_corte`.

    Volumen (unidades) de los últimos `ventana` días hábiles; se ordena de mayor a menor y un par
    entra a 'cabeza' si el volumen acumulado *antes* de él es < cortes[0] del total, a 'medio' si es
    < cortes[1], y el resto es 'cola' (los pares sin volumen van a 'cola'). Es la misma definición
    de `12_segmentacion_volumen.ipynb`, que la calcula por fold con `train_end`; aquí se usa para
    exportar los modelos con el estrato vigente a la fecha del último dato.
    Devuelve un DataFrame con codigo_item, sucursal, vol_365d y estrato."""
    diario = leer_panel()
    fechas, _ = leer_calendario_habil()
    ancha = (diario.pivot_table(index="fecha", columns=["codigo_item", "sucursal"], values="unidades",
                                aggfunc="sum", fill_value=0)
             .reindex(fechas, fill_value=0).astype("float32"))
    n = fechas.searchsorted(pd.Timestamp(fecha_corte), side="right")
    vol = ancha.to_numpy()[max(0, n - ventana):n].sum(axis=0)
    df = pd.DataFrame({"codigo_item": ancha.columns.get_level_values(0).astype(str),
                       "sucursal": ancha.columns.get_level_values(1).astype(str), "vol_365d": vol})
    df = df.sort_values("vol_365d", ascending=False, kind="stable").reset_index(drop=True)
    total = df["vol_365d"].sum()
    previo = (df["vol_365d"].cumsum() - df["vol_365d"]) / total
    df["estrato"] = np.where(previo < cortes[0], "cabeza", np.where(previo < cortes[1], "medio", "cola"))
    df.loc[df["vol_365d"] <= 0, "estrato"] = "cola"
    return df
