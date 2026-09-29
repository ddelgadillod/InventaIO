#!/usr/bin/env python3
"""
INV-60 — Utilidades de calendario para etl_real/.

Duplicado intencional de cargar_festivos()/construir_dias_puente() de
parse_ventas_dir.py (repo ventas2) -- para que este pipeline no dependa
de otro repo en tiempo de ejecución. Si se corrige la lógica de puentes
allá, hay que replicar el cambio aquí a mano (son ~15 líneas, no vale
la pena una dependencia cruzada entre repos por esto).

INV-20 -- se suman las marcas de calendario comercial que calculaba
notebooks/03_calendario_estacionalidad.ipynb (Semana Santa, bloques de
diciembre, prima) y la regla de cierre del negocio, para que vivan en
dim_tiempo y no solo en el notebook.
"""
import csv
from datetime import date, timedelta
from pathlib import Path


def cargar_festivos(path: Path) -> dict:
    """Carga el CSV de festivos (columnas fecha,nombre_festivo) a un dict
    {fecha_iso: nombre_festivo}."""
    festivos = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            festivos[row["fecha"]] = row["nombre_festivo"]
    return festivos


def construir_dias_semana_santa(festivos: dict, dias_antes: int, dias_despues: int) -> set:
    """INV-20 -- fechas ISO de la ventana [Jueves Santo - dias_antes,
    Jueves Santo + dias_despues] de cada año, ambos extremos incluidos
    (misma ventana que notebooks/03_calendario_estacionalidad.ipynb)."""
    fechas = set()
    for fecha_iso, nombre in festivos.items():
        if nombre == "Jueves Santo":
            jueves = date.fromisoformat(fecha_iso)
            for k in range(-dias_antes, dias_despues + 1):
                fechas.add((jueves + timedelta(days=k)).isoformat())
    return fechas


def bloque_diciembre(d: date, novena: tuple, nochebuena_navidad: tuple,
                     fin_de_anio: tuple, enero_postnavidad_max_dia: int) -> str:
    """INV-20 -- sub-bloque de la temporada navideña (notebook 03):
    novena, nochebuena_navidad, fin_de_anio, enero_postnavidad o ninguno.
    Los rangos son (día inicial, día final) de diciembre, inclusivos."""
    if d.month == 12 and novena[0] <= d.day <= novena[1]:
        return "novena"
    if d.month == 12 and nochebuena_navidad[0] <= d.day <= nochebuena_navidad[1]:
        return "nochebuena_navidad"
    if d.month == 12 and fin_de_anio[0] <= d.day <= fin_de_anio[1]:
        return "fin_de_anio"
    if d.month == 1 and d.day <= enero_postnavidad_max_dia:
        return "enero_postnavidad"
    return "ninguno"


def es_periodo_prima(d: date, junio: tuple, diciembre: tuple) -> bool:
    """INV-20 -- días de pago de la prima de servicios (notebook 03)."""
    return ((d.month == 6 and junio[0] <= d.day <= junio[1])
            or (d.month == 12 and diciembre[0] <= d.day <= diciembre[1]))


def es_cierre_programado(fecha_iso: str, festivos: dict, festivos_cierre: list) -> bool:
    """INV-20 -- el negocio no abre en los festivos de `festivos_cierre`
    (confirmado: 1 de enero y Viernes Santo). Es la regla con la que se
    proyectan los días hábiles futuros; los días hábiles pasados salen de
    las ventas observadas."""
    return festivos.get(fecha_iso) in festivos_cierre


def construir_dias_puente(festivos: dict) -> set:
    """Si el festivo cae lunes, sábado y domingo anteriores son puente.
    Si no cae lunes, solo el día calendario inmediato anterior."""
    puente = set()
    for fecha_iso in festivos:
        d = date.fromisoformat(fecha_iso)
        if d.isoweekday() == 1:  # lunes
            puente.add((d - timedelta(days=1)).isoformat())
            puente.add((d - timedelta(days=2)).isoformat())
        else:
            puente.add((d - timedelta(days=1)).isoformat())
    return puente
