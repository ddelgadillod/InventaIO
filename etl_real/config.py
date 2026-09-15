"""
INV-60 — Configuración compartida del pipeline de construcción del DW real.

Reemplaza el dataset simulado (Kaggle Favorita 2013-2017) que hoy carga
InventaIO por el dataset real producido por el repo ventas2 (ETL de
ventas POS Siigo, 2023-2025). Ver docs/INV-60-compatibilidad-datos.md y
docs/INV-60-notas-migracion-dw.md.

Este pipeline vive en InventaIO pero NO importa código de ventas2 en
tiempo de ejecución (ver etl_real/calendario_utils.py) -- los tres
insumos de entrada (ventas_tidy.csv, festivos_colombia_2022_2026.csv,
terminal_sucursal.csv) son artefactos que ese otro repo produce; aquí
solo se leen desde data/raw_real/ (o la ruta que indiquen las variables
de entorno de abajo). Ver docs/INV-60-tutorial-migracion.md para cómo
llevarlos ahí.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_REAL = BASE_DIR / "data" / "raw_real"

VENTAS_TIDY_CSV = Path(os.environ.get("VENTAS_TIDY_CSV", DATA_RAW_REAL / "ventas_tidy.csv"))
FESTIVOS_CSV = Path(os.environ.get("FESTIVOS_CSV", DATA_RAW_REAL / "festivos_colombia_2022_2026.csv"))
TERMINAL_SUCURSAL_CSV = Path(os.environ.get("TERMINAL_SUCURSAL_CSV", DATA_RAW_REAL / "terminal_sucursal.csv"))

# Distinto de data/processed/ (que usa el pipeline Favorita/etl/) para
# no mezclar los dos datasets en el mismo directorio de salida.
SALIDA_DIR = BASE_DIR / "data" / "processed_real"

RANDOM_SEED = 42  # mismo valor que usa InventaIO, por consistencia documental

# ── Sucursales ──────────────────────────────────────────────────────
# Nombres reales (crosswalk terminal_pos->sucursal de INV-61), no los
# ficticios de InventaIO (Sucursal Principal/Norte/Sur). Se agrega
# SIN_SUCURSAL como sucursal placeholder (no física) para que las ventas
# de terminal FV2 (facturación electrónica sin punto de venta) tengan un
# FK válido en fact_ventas sin descartarlas en silencio.
SUCURSALES_REALES = ["PRINCIPAL", "LA 21", "GLORIETA"]
SUCURSAL_SIN_TERMINAL = "SIN_SUCURSAL"

# ── Categorías objetivo (mismo vocabulario que InventaIO, para poder ──
# reusar sus tablas de márgenes/precios/proveedores si hace falta más
# adelante) ────────────────────────────────────────────────────────
CATEGORIAS_OBJETIVO = [
    "Abarrotes", "Bebidas", "Lácteos", "Cárnicos", "Panadería",
    "Congelados", "Frutas y verduras", "Avícola", "Mariscos",
    "Huevos", "Cuidado personal", "Aseo hogar", "Hogar",
    "Delicatessen", "Bebé",
]

CATEGORIAS_PERECEDERAS = [
    "Frutas y verduras", "Huevos", "Cárnicos", "Avícola", "Mariscos", "Lácteos",
]

# ── Heurística de clasificación por palabras clave ───────────────────
# Se evalúa en orden: la primera categoría cuyo patrón matchea en el
# nombre del producto gana. Es un best-effort documentado, no una
# clasificación validada por negocio (ver docs/INV-60-notas-migracion-dw.md).
CATEGORIA_KEYWORDS = [
    ("Huevos", ["HUEVO"]),
    ("Avícola", ["POLLO", "PECHUGA", "MUSLO", "ALITA", "GALLINA"]),
    ("Mariscos", ["PESCADO", "CAMARON", "ATUN", "SARDINA", "MARISCO", "TILAPIA"]),
    ("Cárnicos", ["CARNE", "CERDO", "CHULETA", "LOMO", "MOLIDA", "CHORIZO",
                  "SALCHICHA", "JAMON", "TOCINETA", "MORTADELA", "COSTILLA"]),
    ("Lácteos", ["LECHE", "QUESO", "YOGUR", "YOGURT", "KUMIS", "AREQUIPE",
                 "MANTEQUILLA", "CREMA DE LECHE", "KOUMIS"]),
    ("Panadería", ["PAN ", "PANDEBONO", "AREPA", "PONQ", "TORTA", "GALLETA",
                   "GALL ", "PASTEL", "BIZCOCHO"]),
    ("Congelados", ["CONGELAD", "HELADO", "NUGGET", "PAPA FRITA CONG"]),
    ("Frutas y verduras", ["MANZANA", "BANANO", "PAPA", "TOMATE", "CEBOLLA",
                            "FRUTA", "VERDURA", "LECHUGA", "ZANAHORIA",
                            "LIMON", "NARANJA", "AGUACATE", "PLATANO", "MORA",
                            "COLIFLOR"]),
    ("Bebé", ["PAÑAL", "BEBE", "FORMULA INFANTIL", "TOALLITA HUMEDA",
              "NUTRIBEN", "PAÑITOS HUMEDOS", "TOALLITA HUGGIES"]),
    ("Cuidado personal", ["SHAMPOO", "CHAMPU", "JABON DE TOCADOR", "DESOD",
                           "CREMA DENTAL", "COLGATE", "PANTENE", "PROTECTOR",
                           "TOALLA HIGIENICA", "AFEITAR", "CEPILLO DENTAL",
                           "ENJUAGUE BUCAL"]),
    ("Aseo hogar", ["DET ", "DETERGENTE", "JABON EN POLVO", "JABON LOZA",
                     "LAVALOZA", "PAPEL HIG", "LIMPIA", "CLORO", "AMBIENTAL",
                     "ESCOBA", "TRAPERO", "FAB ", "ARIEL", "BLANCOX",
                     "SUAVITEL", "VARSOL"]),
    ("Bebidas", ["CERVEZA", "GASEOSA", "JUGO", "AGUA", "MALTA", "VINO",
                 "WHISKY", "AGUARDIENTE", "RON ", "CAFE", "BEBIDA",
                 "REFRESCO", "POLA ", "COLA ", "TE HELADO"]),
    ("Hogar", ["VELA", "VASO", "OLLA", "SARTEN", "COBIJA", "BOMBILLO",
               "PILA ", "BATERIA"]),
]
DEFAULT_CATEGORIA = "Abarrotes"  # mismo fallback que usa InventaIO

UNIDAD_MEDIDA_PATTERNS = [
    ("kg", r"\bK\.?G\.?S?\b|\bKILO"),
    ("g", r"\bG\.?R?\.?S?\b(?!\w)"),
    ("l", r"\bL\.?T\.?S?\b|\bLITRO"),
    ("ml", r"\bM\.?L\.?S?\b"),
    ("un", r"\bUN\.?D?\.?S?\b|\bUNIDAD"),
]
DEFAULT_UNIDAD_MEDIDA = "unidad"

# ── Proveedores sintéticos ────────────────────────────────────────────
# Inspirado en el precedente de etl/paso_02_sinteticos.py de InventaIO
# (mismo patrón: catálogo fijo de proveedores ficticios asignados por
# categoría), pero la asignación producto->proveedor usa las categorías
# reales clasificadas por CATEGORIA_KEYWORDS, no las de Favorita. No hay
# fuente real de proveedores en los reportes de venta Siigo.
PROVEEDORES_SEED = [
    {"codigo": "PROV-001", "razon_social": "Distribuidora Valle S.A.S.", "nit": "900.123.456-7", "ciudad": "Cali", "lead_time_dias": 3, "categorias": ["Abarrotes", "Bebidas"]},
    {"codigo": "PROV-002", "razon_social": "Lácteos del Cauca Ltda.", "nit": "900.234.567-8", "ciudad": "Popayán", "lead_time_dias": 5, "categorias": ["Lácteos", "Huevos"]},
    {"codigo": "PROV-003", "razon_social": "Carnes Premium Colombia S.A.", "nit": "900.345.678-9", "ciudad": "Cali", "lead_time_dias": 4, "categorias": ["Cárnicos", "Avícola"]},
    {"codigo": "PROV-004", "razon_social": "Panadería Industrial El Trigal", "nit": "900.456.789-0", "ciudad": "Bogotá", "lead_time_dias": 3, "categorias": ["Panadería", "Delicatessen"]},
    {"codigo": "PROV-005", "razon_social": "Frutos del Pacífico S.A.S.", "nit": "900.567.890-1", "ciudad": "Buenaventura", "lead_time_dias": 7, "categorias": ["Frutas y verduras", "Mariscos"]},
    {"codigo": "PROV-006", "razon_social": "Congelados del Sur Ltda.", "nit": "900.678.901-2", "ciudad": "Tuluá", "lead_time_dias": 5, "categorias": ["Congelados"]},
    {"codigo": "PROV-007", "razon_social": "Aseo Total de Colombia S.A.", "nit": "900.789.012-3", "ciudad": "Bogotá", "lead_time_dias": 10, "categorias": ["Aseo hogar", "Cuidado personal"]},
    {"codigo": "PROV-008", "razon_social": "Hogar & Estilo S.A.S.", "nit": "900.890.123-4", "ciudad": "Bucaramanga", "lead_time_dias": 12, "categorias": ["Hogar"]},
    {"codigo": "PROV-009", "razon_social": "NutriBebé Colombia S.A.", "nit": "900.901.234-5", "ciudad": "Bogotá", "lead_time_dias": 15, "categorias": ["Bebé"]},
    {"codigo": "PROV-010", "razon_social": "Importadora Andina Ltda.", "nit": "901.012.345-6", "ciudad": "Cali", "lead_time_dias": 8, "categorias": ["Bebidas", "Abarrotes", "Congelados"]},
]

# ── Parámetros de simulación de inventario ───────────────────────────
# Mismo método que etl/paso_02_sinteticos.py de InventaIO
# (generar_fact_inventario), corrigiendo el sesgo de demanda_diaria
# identificado en docs/INV-14-recomendaciones-eda.md: se divide entre
# todos los días de la ventana activa, no solo entre los días con venta.
INVENTARIO_PARAMS = {
    "dias_stock_minimo": 3,
    "dias_stock_maximo": 30,
    "dias_punto_reorden": 7,
    "variacion_stock_pct": 0.15,
}
