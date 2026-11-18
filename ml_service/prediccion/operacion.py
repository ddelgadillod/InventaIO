"""
InventAI/o — ML Service: fecha de operación (INV-62, pronóstico al día presente).

El servicio pronostica desde la fecha de operación: hoy en Bogotá, o la que fije la variable `FECHA_OPERACION` (pruebas y
demostraciones), nunca antes del último dato. Las features se calculan con el historial hasta el último dato; la ventana del
pronóstico son los días hábiles siguientes a la fecha de operación (los de la historia y, después del último dato, los de
dim_tiempo que no son cierre programado). La medición de INV-62 (`notebooks/19_desfase_pronostico.py`) mostró que con
hasta 90 días hábiles sin datos la cobertura del cuantil de negocio sigue a menos de 0,05 de su objetivo, así que no se
ajusta; la respuesta avisa los días hábiles sin datos.
"""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from prediccion.features import Calendario

ZONA_BOGOTA = timezone(timedelta(hours=-5))        # Colombia no tiene horario de verano


def fecha_operacion(calendario: Calendario, ahora: datetime | None = None) -> pd.Timestamp:
    """`FECHA_OPERACION` (AAAA-MM-DD) si está definida; si no, la fecha de hoy en Bogotá. Nunca antes del último dato."""
    texto = os.environ.get("FECHA_OPERACION", "").strip()
    fecha = pd.Timestamp(texto) if texto else pd.Timestamp((ahora or datetime.now(ZONA_BOGOTA)).date())
    return max(fecha.normalize(), calendario.ultima_fecha)


def dias_habiles_entre(calendario: Calendario, desde, hasta) -> int:
    """Días hábiles en (desde, hasta]: los de la historia y, después del último dato, los de dim_tiempo sin cierre."""
    desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta)
    if hasta <= desde:
        return 0
    historicos = int(((calendario.habiles > desde) & (calendario.habiles <= hasta)).sum())
    marcas = calendario.marcas
    inicio_futuro = max(desde, calendario.ultima_fecha)
    futuros = int(((marcas.index > inicio_futuro) & (marcas.index <= hasta) & ~marcas["es_cierre_programado"].astype(bool)).sum())
    return historicos + futuros


def ventana(calendario: Calendario, inicio, horizonte: int) -> tuple:
    """(primer día, último día) de los `horizonte` días hábiles que siguen a `inicio`."""
    dias = calendario.proximos_habiles(inicio, horizonte)
    return dias[0], dias[-1]
