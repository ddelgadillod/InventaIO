#!/usr/bin/env python3
"""
INV-20 — Atributos de producto de la regla de priorización (condiciones
1-5 de notebooks/02_regla_priorizacion.ipynb), calculados a partir del
nombre y la categoría del producto.

Hasta INV-20 estas reglas solo vivían en el notebook 02, y el modelo de
Nivel 1 las usa como features (cond1..cond5). Se llevan a dim_producto
para que el servicio de predicción y los demás módulos lean exactamente
los mismos atributos desde la bodega. Las reglas son las del notebook,
sin cambios; tests/test_etl_real.py verifica que coinciden producto por
producto con dim_producto_priorizado.parquet cuando ese archivo existe.

| Columna en dim_producto     | Feature del modelo     |
|-----------------------------|------------------------|
| requiere_espacio_bodega     | cond1_espacio_bodega   |
| es_perecedero_estricto      | cond2_perecedero       |
| es_refrigerado              | cond3_refrigerado      |
| es_papel_higienico_grande   | cond4_papel_higienico  |
| es_temporada                | cond5_temporada        |
"""
import re

import config

CORE_UNIDAD = {
    "kg": r"K\.?G\.?S?\b|KILO",
    "g": r"G\.?R?\.?S?\b(?!\w)",
    "l": r"L\.?T\.?S?\b|LITRO",
    "ml": r"M\.?L\.?S?\b",
    "cm3": r"C\.?M\.?3?\b|CC\b",
}
PATRONES_UNIDAD = [
    (u, re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(?<![A-Za-z])(?:" + core + ")", re.IGNORECASE))
    for u, core in CORE_UNIDAD.items()
]
LIQUID_KEYWORDS = re.compile(
    r"LIQUID|\bDET\b|\bBLQ\b|LIMPI|DESENGRASANTE|DESINFECTANTE|SUAVIZANTE|SUAVITEL|"
    r"\bCLORO\b|VARSOL|SHAMPOO|CHAMPU|CHAMP |ACEITE|VINAGRE|JARABE|\bAGUA\b|JUGO|"
    r"GASEOSA|ALCOHOL|ENJUAGUE|LOCION|COLONIA|CERVEZA|\bVINO\b|WHISKY|AGUARDIENTE|\bRON\b|MALTA",
    re.IGNORECASE,
)
CATEGORIAS_LIQUIDAS = {"Bebidas", "Licores", "Aceites y sustitutos"}
LACTEO_LIQUIDO = re.compile(r"LECHE|KUMIS|YOGUR", re.IGNORECASE)
LACTEO_NO_LIQUIDO = re.compile(r"CONDENSADA|POLVO", re.IGNORECASE)
NUMERO_SUELTO = re.compile(r"\*\s*(\d+)(?:\s*(UND|UN|ROLLOS?))?\b", re.IGNORECASE)
LACTEO_NO_REFRIGERADO = re.compile(r"CONDENSADA|EN POLVO|POLVO", re.IGNORECASE)
PAPEL_HIGIENICO = re.compile(r"PAPEL HIG", re.IGNORECASE)
MULTIPLICADOR_ROLLOS = re.compile(r"\*\s*(\d+)\s*(?:UND|UN|ROLLOS?)?\b", re.IGNORECASE)
TEMPORADA_NAVIDENA = re.compile(r"NATILLA|BU[ÑN]UELO", re.IGNORECASE)
GALLETA = re.compile(r"GALLETA", re.IGNORECASE)
NAVIDAD = re.compile(r"NAVID", re.IGNORECASE)


def es_liquido(nombre: str, categoria: str) -> bool:
    if categoria in CATEGORIAS_LIQUIDAS:
        return True
    if categoria == "Lácteos" and LACTEO_LIQUIDO.search(nombre) and not LACTEO_NO_LIQUIDO.search(nombre):
        return True
    return bool(LIQUID_KEYWORDS.search(nombre))


def extraer_tamano(nombre: str, categoria: str) -> tuple:
    """(volumen_cm3, peso_g, tamano_inferido) leídos del nombre. Si hay
    varias medidas se toma la mayor; un "*N" sin unidad (N >= umbral) se
    interpreta como volumen o peso según el producto sea líquido o no."""
    nombre = str(nombre)
    vol_cm3, peso_g = None, None
    for unidad, patron in PATRONES_UNIDAD:
        for m in patron.finditer(nombre):
            v1 = float(m.group(1).replace(",", "."))
            v2 = float(m.group(2).replace(",", ".")) if m.group(2) else None
            val = max(v1, v2) if v2 else v1
            if unidad == "kg":
                peso_g = val * 1000 if peso_g is None else max(peso_g, val * 1000)
            elif unidad == "g":
                peso_g = val if peso_g is None else max(peso_g, val)
            elif unidad == "l":
                vol_cm3 = val * 1000 if vol_cm3 is None else max(vol_cm3, val * 1000)
            else:
                vol_cm3 = val if vol_cm3 is None else max(vol_cm3, val)

    inferido = False
    if vol_cm3 is None and peso_g is None:
        m = NUMERO_SUELTO.search(nombre)
        if m and m.group(2) is None and float(m.group(1)) >= config.UMBRAL_NUMERO_SUELTO_INFERENCIA:
            inferido = True
            val = float(m.group(1))
            if es_liquido(nombre, categoria):
                vol_cm3 = val
            else:
                peso_g = val
    return vol_cm3, peso_g, inferido


def extraer_rollos(nombre: str) -> int:
    m = MULTIPLICADOR_ROLLOS.search(str(nombre))
    return int(m.group(1)) if m else 1


def atributos(nombre: str, categoria: str) -> dict:
    """Las columnas de atributos de dim_producto para un producto."""
    nombre = str(nombre)
    vol_cm3, peso_g, inferido = extraer_tamano(nombre, categoria)
    es_papel = categoria == "Aseo hogar" and bool(PAPEL_HIGIENICO.search(nombre))
    rollos = extraer_rollos(nombre) if es_papel else None
    es_lacteo_no_refrigerado = categoria == "Lácteos" and bool(LACTEO_NO_REFRIGERADO.search(nombre))
    return {
        "volumen_cm3": vol_cm3,
        "peso_g": peso_g,
        "tamano_inferido": inferido,
        "requiere_espacio_bodega": (
            (vol_cm3 is not None and vol_cm3 >= config.UMBRAL_VOLUMEN_CM3)
            or (peso_g is not None and peso_g >= config.UMBRAL_PESO_G)
        ),
        "es_perecedero_estricto": categoria in config.CATEGORIAS_PERECEDERAS_ESTRICTO,
        "es_refrigerado": categoria in config.CATEGORIAS_REFRIGERADAS and not es_lacteo_no_refrigerado,
        "rollos_paquete": rollos,
        "es_papel_higienico_grande": es_papel and rollos >= config.UMBRAL_ROLLOS_PAPEL_HIGIENICO,
        "es_temporada": (
            bool(TEMPORADA_NAVIDENA.search(nombre))
            or (bool(GALLETA.search(nombre)) and bool(NAVIDAD.search(nombre)))
            or categoria == "Licores"
        ),
    }


COLUMNAS = list(atributos("", "").keys())
