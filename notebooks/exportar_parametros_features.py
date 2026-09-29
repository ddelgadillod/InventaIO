#!/usr/bin/env python3
"""
INV-20 — Exporta a models/nivel1_parametros_features.json los parámetros con
los que 07_matriz_as_of.ipynb calculó las features de entrenamiento, para que
ml_service calcule las mismas features leyendo la bodega (Postgres) en vez de
un extracto de la matriz.

Son parámetros del entrenamiento, no datos: se congelan junto a los modelos y
el servicio no los recalcula (los coeficientes de calendario se estimaron en
03 con la historia de entrenamiento; recalcularlos con datos nuevos cambiaría
la feature sin reentrenar el modelo). No modifica los .joblib ni
nivel1_metadata.json.

Verifica antes de escribir que los artefactos que lee son los que usó la
matriz de entrenamiento (huellas de huella_07.json).

    python exportar_parametros_features.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_priorizacion import DW, PARAMS, registrar_huella  # noqa: E402
from exportar_modelos_nivel1 import FEATURES, MODELS_DIR  # noqa: E402

import pandas as pd  # noqa: E402

SALIDA = MODELS_DIR / "nivel1_parametros_features.json"

# Mismo mapeo que EVENTO_A_CONDICION en 07_matriz_as_of.ipynb (celda del
# factor de calendario), expresado sobre columnas de dw.dim_tiempo. Ojo:
# "Quincena (15-17)" usa dim_tiempo.es_quincena (día 15 y último día del mes)
# y los tramos de mes aplican a todos los meses -- así los usó 07 al construir
# la feature, aunque la regresión de 03 los estimó con días 15-17 y solo en
# meses ordinarios. Se conserva la definición de 07 porque es con la que se
# entrenó el modelo (paridad), y queda documentado como inconsistencia a
# revisar en un reentrenamiento.
CONDICIONES_EVENTO = {
    "Festivo": {"columna": "es_festivo", "operador": "verdadero"},
    "Puente festivo": {"columna": "es_puente_festivo", "operador": "verdadero"},
    "Semana Santa": {"columna": "es_semana_santa", "operador": "verdadero"},
    "Período de prima": {"columna": "es_periodo_prima", "operador": "verdadero"},
    "Quincena (15-17)": {"columna": "es_quincena", "operador": "verdadero"},
    "Inicio de mes (1-3)": {"columna": "dia", "operador": "<=", "valor": 3},
    "Fin de mes (>=28)": {"columna": "dia", "operador": ">=", "valor": 28},
    "novena": {"columna": "bloque_diciembre", "operador": "==", "valor": "novena"},
    "nochebuena_navidad": {"columna": "bloque_diciembre", "operador": "==", "valor": "nochebuena_navidad"},
    "fin_de_anio": {"columna": "bloque_diciembre", "operador": "==", "valor": "fin_de_anio"},
    "enero_postnavidad": {"columna": "bloque_diciembre", "operador": "==", "valor": "enero_postnavidad"},
}

# Columnas de dw.dim_producto (etl_real/atributos_producto.py) -> features cond1..cond5
CONDICIONES_PRODUCTO = {
    "cond1_espacio_bodega": "requiere_espacio_bodega",
    "cond2_perecedero": "es_perecedero_estricto",
    "cond3_refrigerado": "es_refrigerado",
    "cond4_papel_higienico": "es_papel_higienico_grande",
    "cond5_temporada": "es_temporada",
}


def construir_parametros() -> dict:
    huella_07 = json.loads((DW / "huella_07.json").read_text())
    esperado = huella_07["entradas"]["efectos_calendario.csv"]
    actual = registrar_huella(["efectos_calendario.csv"])["efectos_calendario.csv"]
    assert actual == esperado, (f"efectos_calendario.csv ({actual}) no es el que usó la matriz de "
                                f"entrenamiento ({esperado}): re-ejecutar 03 y 07 o revisar")

    efectos = pd.read_csv(DW / "efectos_calendario.csv")
    incluidos = efectos.loc[efectos["direccion"].isin(["sube", "baja"])]
    sin_mapeo = set(incluidos["evento"]) - set(CONDICIONES_EVENTO)
    assert not sin_mapeo, f"eventos con efecto confirmado sin condición: {sin_mapeo}"
    eventos = [{"evento": r.evento, "factor": float(r.controlado_x), **CONDICIONES_EVENTO[r.evento]}
               for r in incluidos.itertuples()]

    p07 = huella_07["parametros"]
    return {
        "version": 1,
        "fecha_generacion": datetime.now(timezone.utc).isoformat(),
        "origen": {
            "notebook": "07_matriz_as_of.ipynb",
            "huella_efectos_calendario": esperado,
            "matriz_entrenamiento": huella_07["salidas"].get("matriz_as_of.parquet"),
        },
        "features": FEATURES,
        "horizonte": p07["HORIZONTE"],
        "ventana_trail": p07["HORIZONTE"],
        "ventana_nivel": 60,
        "min_periodos_nivel": 20,
        "min_frecuencia_as_of": p07["MIN_FRECUENCIA_ASOF"],
        "adi_corte": PARAMS["ADI_CORTE"],
        "cv2_corte": PARAMS["CV2_CORTE"],
        "tipos_sucursal_modelo": ["principal", "estandar"],
        "calendario_habil": ("historia: días con al menos una venta neta en el negocio (todas las sucursales, "
                             "sin devoluciones, cantidad > 0), como en 01; futuro: días de dw.dim_tiempo "
                             "posteriores al último dato sin es_cierre_programado"),
        "eventos_calendario": eventos,
        "condiciones_producto": CONDICIONES_PRODUCTO,
    }


def main():
    parametros = construir_parametros()
    SALIDA.write_text(json.dumps(parametros, indent=2, ensure_ascii=False) + "\n")
    print(f"guardado: {SALIDA} ({len(parametros['eventos_calendario'])} eventos de calendario)")


if __name__ == "__main__":
    main()
