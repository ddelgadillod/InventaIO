"""
InventAI/o — ML Service: pronóstico para una fecha o un rango elegidos (INV-79).

- **Fecha de inicio pasada** (hasta el último dato): se pronostica con lo que se sabía el día hábil anterior; la ventana son los
  15 días hábiles siguientes, y si ya pasaron se comparan con lo vendido.
- **Fecha de inicio futura:** las features salen del último dato y la ventana empieza en esa fecha (como el pronóstico al día
  presente de INV-62, con la fecha de operación corrida).
- **Rango** (con `fecha_fin`): solo la mediana, aproximada. Con 15 días hábiles o menos se reparte la de la ventana; con más, se
  encadenan ventanas de 15 con las mismas features y el factor de calendario de cada una. No hay cantidad de reposición: un cuantil
  no se reparte ni se suma (los modelos de 7 y 30 días llegan con INV-80).

Contrato completo en `docs/INV-79-requerimientos.md`.
"""
from dataclasses import dataclass

import pandas as pd

from prediccion.features import Calendario
from prediccion.operacion import dias_habiles_entre, fuera_de_lo_medido

VENTANA = 15            # días hábiles de la ventana del modelo
RANGO_MAXIMO = 90       # días hábiles: lo que cubrió la medición del desfase


class FechaInvalida(ValueError):
    """Una fecha o un rango que no se puede pronosticar (422)."""


@dataclass(frozen=True)
class Tramo:
    """La parte de una ventana de 15 días hábiles que cae dentro del rango. `inicio` es la fecha de operación de esa ventana:
    sus días son los hábiles que la siguen."""
    desde: pd.Timestamp
    hasta: pd.Timestamp
    dias_habiles: int
    inicio: pd.Timestamp


def _dentro_del_calendario(calendario: Calendario, fecha, campo: str) -> pd.Timestamp:
    fecha = pd.Timestamp(fecha).normalize()
    limite = calendario.marcas.index.max()
    if fecha > limite:
        raise FechaInvalida(f"{campo}={fecha.date()} es posterior al calendario de la bodega (llega al {limite.date()}).")
    return fecha


def resolver_inicio(calendario: Calendario, fecha_inicio, operacion_por_defecto) -> tuple:
    """(fecha de los datos, fecha de operación). La ventana son los días hábiles que siguen a la fecha de operación.

    Sin `fecha_inicio`, los datos llegan al último día con ventas y la operación es la de siempre (hoy). Con una fecha pasada,
    los dos son el día hábil anterior a ella (HistoriaInsuficiente si no lo hay). Con una futura, los datos son los últimos y la
    operación es el día anterior a ella, nunca antes del último dato."""
    ultima = calendario.ultima_fecha
    if fecha_inicio is None:
        return calendario.ultimo_habil(ultima), pd.Timestamp(operacion_por_defecto)
    inicio = _dentro_del_calendario(calendario, fecha_inicio, "fecha_inicio")
    if inicio <= ultima:
        datos = calendario.ultimo_habil(inicio - pd.Timedelta(days=1))
        return datos, datos
    return ultima, max(inicio - pd.Timedelta(days=1), ultima)


def tramos_rango(calendario: Calendario, inicio, fecha_fin, ventana: int = VENTANA, maximo: int = RANGO_MAXIMO) -> list:
    """Los días hábiles entre el primer día de la ventana y `fecha_fin`, partidos en ventanas de `ventana` días."""
    fin = _dentro_del_calendario(calendario, fecha_fin, "fecha_fin")
    n = dias_habiles_entre(calendario, inicio, fin)
    if n == 0:
        primero = calendario.proximos_habiles(inicio, 1)[0]
        raise FechaInvalida(f"fecha_fin={fin.date()} es anterior al primer día de la ventana ({primero.date()}).")
    if n > maximo:
        raise FechaInvalida(f"el rango tiene {n} días hábiles; el máximo es {maximo}.")
    dias = calendario.proximos_habiles(inicio, n)
    return [Tramo(desde=dias[k], hasta=dias[min(k + ventana, n) - 1], dias_habiles=min(ventana, n - k),
                  inicio=pd.Timestamp(inicio) if k == 0 else dias[k - 1])
            for k in range(0, n, ventana)]


def ventas_en(unidades: pd.Series | None, desde, hasta, ultima_fecha) -> float | None:
    """Unidades vendidas en [desde, hasta], solo si el tramo está entero dentro de la historia."""
    if unidades is None or pd.Timestamp(hasta) > pd.Timestamp(ultima_fecha):
        return None
    tramo = unidades[(unidades.index >= pd.Timestamp(desde)) & (unidades.index <= pd.Timestamp(hasta))]
    return round(float(tramo.sum()), 2)


def armar_rango(calendario: Calendario, tramos: list, q50_por_tramo: list, unidades: pd.Series | None,
                fecha_datos, ventana: int = VENTANA) -> dict:
    """El objeto `rango` de la respuesta. `q50_por_tramo`: la mediana de la ventana completa de cada tramo."""
    ultima = calendario.ultima_fecha
    partes, total = [], 0.0
    for tramo, q50 in zip(tramos, q50_por_tramo, strict=True):
        parte = q50 * tramo.dias_habiles / ventana
        total += parte
        partes.append({"desde": tramo.desde.date().isoformat(), "hasta": tramo.hasta.date().isoformat(),
                       "dias_habiles": tramo.dias_habiles, "prediccion_q50_aproximada": round(parte, 2),
                       "ventas_reales": ventas_en(unidades, tramo.desde, tramo.hasta, ultima)})
    reales = [p["ventas_reales"] for p in partes]
    return {
        "desde": partes[0]["desde"],
        "hasta": partes[-1]["hasta"],
        "dias_habiles": sum(t.dias_habiles for t in tramos),
        "prediccion_q50_aproximada": round(total, 2),
        "metodo": "reparto" if len(tramos) == 1 else "ventanas_encadenadas",
        "ventanas": partes,
        "ventas_reales": None if None in reales else round(sum(reales), 2),
        "fuera_de_lo_medido": fuera_de_lo_medido(dias_habiles_entre(calendario, fecha_datos, tramos[-1].inicio)),
        "aproximado": True,
    }
