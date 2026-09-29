"""
InventAI/o — ML Service: features de Nivel 1 calculadas desde la bodega
INV-20 (fix): el servicio ya no lee un extracto de matriz_as_of.parquet (esa
matriz es solo para entrenar y validar). Calcula las 14 features del modelo
a partir de la venta diaria del par en la bodega (dw.v_ventas_diarias_netas),
el calendario (dw.dim_tiempo) y los atributos del producto (dw.dim_producto),
con las mismas fórmulas de notebooks/07_matriz_as_of.ipynb y los parámetros
congelados en models/nivel1_parametros_features.json.

Funciones puras (sin I/O): tests/test_features.py las contrasta con una
réplica del cálculo de 07 y tests/test_paridad_matriz.py con la matriz real.

Dos fechas, como en 07:
- `fecha_origen`: el día as-of del pronóstico. Las features dinámicas
  (trail_15, trail_15_prev, nivel_medio_60d, dias_desde_ultima_venta) usan
  la historia hasta ese día, y el factor de calendario los 15 días hábiles
  siguientes.
- `fecha_corte_estatica`: hasta dónde se miden las features estáticas
  (frecuencia, ADI, CV², racha). En 07 era el train_end del fold; en
  producción es la misma fecha_origen.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


class HistoriaInsuficiente(Exception):
    """El par no tiene historia suficiente para el modelo (mismo criterio de cold start que 07)."""


class CalendarioInsuficiente(Exception):
    """dim_tiempo no cubre los días hábiles del horizonte (hay que extender el calendario en el ETL)."""


@dataclass(frozen=True)
class Calendario:
    """Días hábiles históricos (días con venta neta en el negocio, como en 01)
    y las marcas de dw.dim_tiempo indexadas por fecha."""
    habiles: pd.DatetimeIndex
    marcas: pd.DataFrame

    @property
    def ultima_fecha(self) -> pd.Timestamp:
        return self.habiles[-1]

    def habiles_hasta(self, fecha) -> pd.DatetimeIndex:
        return self.habiles[self.habiles <= pd.Timestamp(fecha)]

    def ultimo_habil(self, fecha) -> pd.Timestamp:
        """Último día hábil histórico en o antes de `fecha`."""
        previos = self.habiles_hasta(fecha)
        if len(previos) == 0:
            raise HistoriaInsuficiente(f"no hay días con venta antes de {pd.Timestamp(fecha).date()}")
        return previos[-1]

    def proximos_habiles(self, fecha_origen, n: int) -> pd.DatetimeIndex:
        """Los n días hábiles que siguen a fecha_origen: los históricos mientras
        haya datos y, después del último dato, los días de dim_tiempo que no
        son cierre programado (1 de enero, Viernes Santo)."""
        fecha_origen = pd.Timestamp(fecha_origen)
        historicos = self.habiles[self.habiles > fecha_origen]
        desde = max(fecha_origen, self.ultima_fecha)
        futuros = self.marcas.index[(self.marcas.index > desde) & ~self.marcas["es_cierre_programado"].astype(bool)]
        dias = historicos.append(futuros)[:n]
        if len(dias) < n:
            raise CalendarioInsuficiente(
                f"dim_tiempo no cubre {n} días hábiles después de {fecha_origen.date()} "
                f"(llega a {self.marcas.index.max().date()})")
        return dias


def _evento_activo(marcas: pd.DataFrame, evento: dict) -> np.ndarray:
    col = marcas[evento["columna"]]
    op = evento["operador"]
    if op == "verdadero":
        return col.fillna(False).astype(bool).to_numpy()
    if op == "<=":
        return (col <= evento["valor"]).to_numpy()
    if op == ">=":
        return (col >= evento["valor"]).to_numpy()
    if op == "==":
        return (col == evento["valor"]).to_numpy()
    raise ValueError(f"operador desconocido en eventos_calendario: {op}")


def factor_calendario(calendario: Calendario, fecha_origen, parametros: dict) -> float:
    """Media, sobre los próximos `horizonte` días hábiles, del producto de los
    efectos de calendario activos cada día (factor_calendario_ventana de 07)."""
    dias = calendario.proximos_habiles(fecha_origen, parametros["horizonte"])
    marcas = calendario.marcas.reindex(dias)
    factor = np.ones(len(dias))
    for evento in parametros["eventos_calendario"]:
        factor[_evento_activo(marcas, evento)] *= evento["factor"]
    return float(factor.mean())


def _racha_max_ceros(x: np.ndarray) -> float:
    ceros = (x == 0).astype(np.int8)
    if not ceros.any():
        return 0.0
    d = np.diff(np.concatenate(([0], ceros, [0])))
    return float((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max())


def features_par(unidades: pd.Series, calendario: Calendario, fecha_origen, fecha_corte_estatica,
                 parametros: dict, atributos: dict) -> dict:
    """Features del par a `fecha_origen`.

    `unidades`: venta diaria neta del par (índice fecha, solo días con venta);
    los días hábiles sin venta cuentan como 0, como en la rejilla de 07.
    `atributos`: columnas de dw.dim_producto de parametros["condiciones_producto"].
    Lanza HistoriaInsuficiente con el mismo criterio de cold start de 07."""
    fecha_origen = pd.Timestamp(fecha_origen)
    fecha_corte_estatica = pd.Timestamp(fecha_corte_estatica)
    habiles = calendario.habiles_hasta(fecha_origen)
    if len(habiles) == 0 or habiles[-1] != fecha_origen:
        raise ValueError(f"{fecha_origen.date()} no es un día hábil de la historia")
    # 07 guardó la rejilla de ventas en float32 y las features estáticas y
    # dias_desde_ultima_venta en float32: se replica esa precisión para que el
    # modelo vea exactamente la representación con la que se entrenó (un valor
    # justo en el umbral de un corte de árbol cambia de lado con el redondeo).
    x32 = unidades.reindex(habiles, fill_value=0.0).to_numpy(dtype=np.float32)
    x = x32.astype(float)
    i = len(x) - 1

    h = parametros["ventana_trail"]
    trail = x[i - h + 1:i + 1].sum() if i + 1 >= h else np.nan
    trail_prev = x[i - 2 * h + 1:i - h + 1].sum() if i + 1 >= 2 * h else np.nan
    ventana = x[max(0, i - parametros["ventana_nivel"] + 1):i + 1]
    nivel = ventana.mean() if len(ventana) >= parametros["min_periodos_nivel"] else np.nan
    con_venta = np.flatnonzero(x > 0)
    dias_desde = float(i - con_venta[-1]) if con_venta.size else np.nan

    # Estáticas sobre la rejilla float32, con la media y el desvío también en
    # float32 como en 07 (el CV² difiere en el último bit si se calcula en float64).
    sub = x32[:int((habiles <= fecha_corte_estatica).sum())]
    pos = np.flatnonzero(sub > 0)
    frecuencia = float(pos.size)
    adi = cv2 = np.nan
    if pos.size >= 2:
        adi = float(np.diff(pos).mean())
        vals = sub[pos]
        media = vals.mean()
        if media > 0:
            cv2 = float((vals.std(ddof=1) / media) ** 2) if vals.size > 1 else 0.0
    racha = _racha_max_ceros(sub)

    if frecuencia < parametros["min_frecuencia_as_of"]:
        raise HistoriaInsuficiente(
            f"{int(frecuencia)} días con venta hasta {fecha_corte_estatica.date()} "
            f"(el modelo exige al menos {parametros['min_frecuencia_as_of']})")
    if np.isnan(trail) or np.isnan(trail_prev):
        raise HistoriaInsuficiente(f"menos de {2 * h} días hábiles de historia hasta {fecha_origen.date()}")

    if np.isnan(adi) or np.isnan(cv2):
        patron = "sin_datos"
    elif adi < parametros["adi_corte"]:
        patron = "suave" if cv2 < parametros["cv2_corte"] else "erratico"
    else:
        patron = "intermitente" if cv2 < parametros["cv2_corte"] else "lumpy"

    f32 = lambda v: float(np.float32(v))  # noqa: E731 -- precisión de las columnas float32 de 07
    fila = {
        "trail_15": float(trail),
        "trail_15_prev": float(trail_prev),
        "nivel_medio_60d": float(nivel),
        "dias_desde_ultima_venta": f32(dias_desde),
        "frecuencia_as_of": f32(frecuencia),
        "adi_as_of": f32(adi),
        "cv2_as_of": f32(cv2),
        "racha_max_as_of": f32(racha),
        "factor_calendario_ventana": factor_calendario(calendario, fecha_origen, parametros),
        "patron_as_of": patron,
        "familia_modelo": "suave" if patron == "suave" else "intermitente",
        "fecha_origen": fecha_origen,
    }
    for feature, columna in parametros["condiciones_producto"].items():
        fila[feature] = int(bool(atributos[columna]))
    return fila


def fila_para_motor(features: dict, codigo_item: str, sucursal: str) -> pd.DataFrame:
    """DataFrame de 1 fila con las columnas que espera prediccion.motor.predecir."""
    return pd.DataFrame([{**features, "codigo_item": codigo_item, "sucursal": sucursal}])


def determinar_rama(fila) -> str:
    """Misma taxonomía de 07/08: familia_modelo (suave/intermitente) +
    cond2_perecedero decide entre las 3 ramas del modelo."""
    if fila["familia_modelo"] == "intermitente":
        return "intermitente"
    return "suave_perecedero" if int(fila["cond2_perecedero"]) == 1 else "suave_no_perecedero"
