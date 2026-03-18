"""
InventAI/o — Configuración del pipeline ETL
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / "data" / "raw"
DATA_PROCESSED = BASE_DIR / "data" / "processed"

# ── Database ───────────────────────────────────────────
POSTGRES_USER = os.getenv("POSTGRES_USER", "inventaio_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "inventaio_pass_2025")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "inventaio")

DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# ── Seed ───────────────────────────────────────────────
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))

# ── Sucursales ─────────────────────────────────────────
SUCURSALES = {
    1: {
        "nombre": "Sucursal Principal",
        "ciudad": "Centro",
        "tipo": "principal",
        "cluster": 1,
        "factor_volumen": 5.0,
    },
    2: {
        "nombre": "Sucursal Norte",
        "ciudad": "Norte",
        "tipo": "estandar",
        "cluster": 2,
        "factor_volumen": 1.0,
    },
    3: {
        "nombre": "Sucursal Sur",
        "ciudad": "Sur",
        "tipo": "estandar",
        "cluster": 2,
        "factor_volumen": 1.0,
    },
}

# ── Categorías InventAI/o (15) ─────────────────────────
FAMILIA_A_CATEGORIA = {
    "GROCERY I": "Abarrotes",
    "GROCERY II": "Abarrotes",
    "BEVERAGES": "Bebidas",
    "CLEANING": "Aseo hogar",
    "DAIRY": "Lácteos",
    "MEATS": "Cárnicos",
    "BREAD/BAKERY": "Panadería",
    "FROZEN FOODS": "Congelados",
    "DELI": "Delicatessen",
    "PERSONAL CARE": "Cuidado personal",
    "PRODUCE": "Frutas y verduras",
    "POULTRY": "Avícola",
    "SEAFOOD": "Mariscos",
    "EGGS": "Huevos",
    "BABY CARE": "Bebé",
    "PREPARED FOODS": "Delicatessen",
    "LIQUOR,WINE,BEER": "Bebidas",
    "HOME AND KITCHEN I": "Hogar",
    "HOME AND KITCHEN II": "Hogar",
    "HOME APPLIANCES": "Hogar",
    "MAGAZINES": "Abarrotes",
    "SCHOOL AND OFFICE SUPPLIES": "Abarrotes",
    "PET SUPPLIES": "Abarrotes",
    "LADIESWEAR": "Abarrotes",
    "LINGERIE": "Abarrotes",
    "AUTOMOTIVE": "Abarrotes",
    "PLAYERS AND ELECTRONICS": "Abarrotes",
    "HARDWARE": "Hogar",
    "CELEBRATION": "Abarrotes",
    "LAWN AND GARDEN": "Hogar",
    "HOME CARE": "Aseo hogar",
}

CATEGORIAS_OBJETIVO = [
    "Abarrotes", "Bebidas", "Lácteos", "Cárnicos", "Panadería",
    "Congelados", "Frutas y verduras", "Avícola", "Mariscos",
    "Huevos", "Cuidado personal", "Aseo hogar", "Hogar",
    "Delicatessen", "Bebé",
]

# ── Márgenes por categoría ─────────────────────────────
MARGENES_POR_CATEGORIA = {
    "Abarrotes": 0.35, "Bebidas": 0.30, "Lácteos": 0.22,
    "Cárnicos": 0.20, "Panadería": 0.40, "Congelados": 0.28,
    "Frutas y verduras": 0.35, "Avícola": 0.18, "Mariscos": 0.25,
    "Huevos": 0.15, "Cuidado personal": 0.40, "Aseo hogar": 0.38,
    "Hogar": 0.45, "Delicatessen": 0.30, "Bebé": 0.32,
}

# ── Rango de precios base por categoría (COP) ──────────
PRECIOS_BASE_RANGO = {
    "Abarrotes":         (1_500, 25_000),
    "Bebidas":           (1_200, 15_000),
    "Lácteos":           (2_000, 18_000),
    "Cárnicos":          (5_000, 45_000),
    "Panadería":         (1_000, 8_000),
    "Congelados":        (3_000, 22_000),
    "Frutas y verduras": (800, 12_000),
    "Avícola":           (4_000, 30_000),
    "Mariscos":          (8_000, 55_000),
    "Huevos":            (500, 18_000),
    "Cuidado personal":  (3_000, 35_000),
    "Aseo hogar":        (2_000, 28_000),
    "Hogar":             (5_000, 80_000),
    "Delicatessen":      (3_500, 25_000),
    "Bebé":              (5_000, 45_000),
}

# ── Festivos colombianos (generados programáticamente) ──
# Ley 51 de 1983 (Ley Emiliani): traslada ciertos festivos al lunes siguiente.
# Ref: https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=4954

from datetime import date, timedelta


def _pascua(anio: int) -> date:
    """Calcula Domingo de Pascua con el algoritmo anónimo gregoriano."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _siguiente_lunes(fecha: date) -> date:
    """Si la fecha no cae lunes, la traslada al lunes siguiente (Ley Emiliani)."""
    if fecha.weekday() == 0:  # ya es lunes
        return fecha
    dias_hasta_lunes = (7 - fecha.weekday()) % 7
    if dias_hasta_lunes == 0:
        dias_hasta_lunes = 7
    return fecha + timedelta(days=dias_hasta_lunes)


def generar_festivos_colombia(anio_inicio: int = 2010,
                               anio_fin: int = 2025) -> dict:
    """
    Genera todos los festivos oficiales de Colombia para un rango de años.

    Retorna dict {str(fecha): nombre_festivo} con 18 festivos por año.

    Tipos de festivos:
    - Fijos inamovibles: caen siempre en su fecha calendario.
    - Fijos Emiliani: se trasladan al lunes siguiente si no caen lunes.
    - Relativos a Pascua inamovibles: dependen de Pascua, no se trasladan.
    - Relativos a Pascua Emiliani: dependen de Pascua, se trasladan al lunes.
    """
    festivos = {}

    def _agregar(fecha_iso, nombre):
        """Agrega festivo, combinando nombres si hay colisión de fecha."""
        if fecha_iso in festivos:
            festivos[fecha_iso] = f"{festivos[fecha_iso]} / {nombre}"
        else:
            festivos[fecha_iso] = nombre

    for anio in range(anio_inicio, anio_fin + 1):
        pascua = _pascua(anio)

        # ── Fijos inamovibles (6) ──────────────────────────
        fijos = [
            (date(anio, 1, 1),   "Año Nuevo"),
            (date(anio, 5, 1),   "Día del Trabajo"),
            (date(anio, 7, 20),  "Día de la Independencia"),
            (date(anio, 8, 7),   "Batalla de Boyacá"),
            (date(anio, 12, 8),  "Inmaculada Concepción"),
            (date(anio, 12, 25), "Navidad"),
        ]

        # ── Fijos Emiliani (7) — trasladados al lunes ─────
        emiliani_fijos = [
            (date(anio, 1, 6),   "Día de los Reyes Magos"),
            (date(anio, 3, 19),  "Día de San José"),
            (date(anio, 6, 29),  "San Pedro y San Pablo"),
            (date(anio, 8, 15),  "Asunción de la Virgen"),
            (date(anio, 10, 12), "Día de la Raza"),
            (date(anio, 11, 1),  "Todos los Santos"),
            (date(anio, 11, 11), "Independencia de Cartagena"),
        ]

        # ── Relativos a Pascua inamovibles (2) ─────────────
        pascua_fijos = [
            (pascua - timedelta(days=3), "Jueves Santo"),
            (pascua - timedelta(days=2), "Viernes Santo"),
        ]

        # ── Relativos a Pascua Emiliani (3) ────────────────
        pascua_emiliani = [
            (pascua + timedelta(days=43), "Ascensión del Señor"),
            (pascua + timedelta(days=64), "Corpus Christi"),
            (pascua + timedelta(days=71), "Sagrado Corazón"),
        ]

        # Agregar fijos inamovibles
        for fecha, nombre in fijos:
            _agregar(fecha.isoformat(), nombre)

        # Agregar fijos Emiliani (trasladados al lunes)
        for fecha, nombre in emiliani_fijos:
            _agregar(_siguiente_lunes(fecha).isoformat(), nombre)

        # Agregar relativos a Pascua inamovibles
        for fecha, nombre in pascua_fijos:
            _agregar(fecha.isoformat(), nombre)

        # Agregar relativos a Pascua Emiliani (trasladados al lunes)
        for fecha, nombre in pascua_emiliani:
            _agregar(_siguiente_lunes(fecha).isoformat(), nombre)

    return festivos


# Generar festivos 2010–2025 (288 festivos = 18 por año × 16 años)
FESTIVOS_COLOMBIA = generar_festivos_colombia(2010, 2025)

# ── Proveedores sintéticos ─────────────────────────────
PROVEEDORES_SEED = [
    {"codigo": "PROV-001", "razon_social": "Distribuidora Valle S.A.S.", "nit": "900.123.456-7", "ciudad": "Tunja", "lead_time_dias": 3, "categorias": ["Abarrotes", "Bebidas"]},
    {"codigo": "PROV-002", "razon_social": "Lácteos del Cauca Ltda.", "nit": "900.234.567-8", "ciudad": "Bogotá", "lead_time_dias": 5, "categorias": ["Lácteos", "Huevos"]},
    {"codigo": "PROV-003", "razon_social": "Carnes Premium Colombia S.A.", "nit": "900.345.678-9", "ciudad": "Tunja", "lead_time_dias": 4, "categorias": ["Cárnicos", "Avícola"]},
    {"codigo": "PROV-004", "razon_social": "Panadería Industrial El Trigal", "nit": "900.456.789-0", "ciudad": "Bogotá", "lead_time_dias": 3, "categorias": ["Panadería", "Delicatessen"]},
    {"codigo": "PROV-005", "razon_social": "Frutos del Pacífico S.A.S.", "nit": "900.567.890-1", "ciudad": "Bogotá", "lead_time_dias": 7, "categorias": ["Frutas y verduras", "Mariscos"]},
    {"codigo": "PROV-006", "razon_social": "Congelados del Sur Ltda.", "nit": "900.678.901-2", "ciudad": "Tunja", "lead_time_dias": 5, "categorias": ["Congelados"]},
    {"codigo": "PROV-007", "razon_social": "Aseo Total de Colombia S.A.", "nit": "900.789.012-3", "ciudad": "Bogotá", "lead_time_dias": 10, "categorias": ["Aseo hogar", "Cuidado personal"]},
    {"codigo": "PROV-008", "razon_social": "Hogar & Estilo S.A.S.", "nit": "900.890.123-4", "ciudad": "Bucaramanga", "lead_time_dias": 12, "categorias": ["Hogar"]},
    {"codigo": "PROV-009", "razon_social": "NutriBebé Colombia S.A.", "nit": "900.901.234-5", "ciudad": "Bogotá", "lead_time_dias": 15, "categorias": ["Bebé"]},
    {"codigo": "PROV-010", "razon_social": "Importadora Andina Ltda.", "nit": "901.012.345-6", "ciudad": "Tunja", "lead_time_dias": 8, "categorias": ["Bebidas", "Abarrotes", "Congelados"]},
]

# ── Parámetros de inventario ───────────────────────────
INVENTARIO_PARAMS = {
    "dias_stock_minimo": 3,
    "dias_stock_maximo": 30,
    "dias_punto_reorden": 7,
    "variacion_stock_pct": 0.15,
}

# ── Productos por categoría (~200 total) ───────────────
PRODUCTOS_POR_CATEGORIA = {
    "Abarrotes": 50, "Bebidas": 38, "Lácteos": 27, "Cárnicos": 22,
    "Panadería": 18, "Congelados": 18, "Frutas y verduras": 30,
    "Avícola": 12, "Mariscos": 9, "Huevos": 8, "Cuidado personal": 22,
    "Aseo hogar": 18, "Hogar": 12, "Delicatessen": 8, "Bebé": 7,
}