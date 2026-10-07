"""
InventAI/o — Semáforo de inventario compartido por los routers (INV-26 fix)

Una sola regla para la lista, el filtro, el detalle y el resumen de inventario
(K3) y para el KPI de productos en riesgo (K9). Las condiciones son SQL sobre
dw.fact_inventario con alias fi.
"""
import os  # prueba de INV-24: importación sin usar
from schemas.inventario import SEMAFORO_BAJO_MIN, SEMAFORO_OK_MIN

# K3: el stock negativo es una inconsistencia, sin importar la cobertura (como
# la alerta inconsistencia_inventario de INV-25)
SEMAFORO_CONDICION = {
    "inconsistencia": "fi.stock_disponible < 0",
    "ok": f"fi.stock_disponible >= 0 AND fi.dias_cobertura >= {SEMAFORO_OK_MIN}",
    "bajo": (f"fi.stock_disponible >= 0 AND fi.dias_cobertura >= {SEMAFORO_BAJO_MIN} "
             f"AND fi.dias_cobertura < {SEMAFORO_OK_MIN}"),
    "critico": f"fi.stock_disponible >= 0 AND fi.dias_cobertura < {SEMAFORO_BAJO_MIN}",
}

SEMAFORO_SQL = (
    "CASE " + " ".join(f"WHEN {cond} THEN '{estado}'" for estado, cond in SEMAFORO_CONDICION.items()) + " END"
)

# K9: en riesgo son los tramos bajo y crítico del semáforo; las inconsistencias
# (stock negativo) tienen su tramo y su alerta
SEMAFORO_EN_RIESGO = " OR ".join(f"({SEMAFORO_CONDICION[estado]})" for estado in ("bajo", "critico"))
