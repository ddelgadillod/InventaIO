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
        "ciudad": "Cali",
        "tipo": "principal",
        "cluster": 1,
        "factor_volumen": 5.0,
    },
    2: {
        "nombre": "Sucursal Norte",
        "ciudad": "Palmira",
        "tipo": "estandar",
        "cluster": 2,
        "factor_volumen": 1.0,
    },
    3: {
        "nombre": "Sucursal Sur",
        "ciudad": "Tuluá",
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

# ── Festivos colombianos ────────────────────────────────
FESTIVOS_COLOMBIA = {
    "2023-01-01": "Año Nuevo", "2023-01-09": "Día de los Reyes Magos",
    "2023-03-20": "Día de San José", "2023-04-06": "Jueves Santo",
    "2023-04-07": "Viernes Santo", "2023-05-01": "Día del Trabajo",
    "2023-05-22": "Ascensión del Señor", "2023-06-12": "Corpus Christi",
    "2023-06-19": "Sagrado Corazón", "2023-07-03": "San Pedro y San Pablo",
    "2023-07-20": "Día de la Independencia", "2023-08-07": "Batalla de Boyacá",
    "2023-08-21": "Asunción de la Virgen", "2023-10-16": "Día de la Raza",
    "2023-11-06": "Todos los Santos", "2023-11-13": "Independencia de Cartagena",
    "2023-12-08": "Inmaculada Concepción", "2023-12-25": "Navidad",
    "2024-01-01": "Año Nuevo", "2024-01-08": "Día de los Reyes Magos",
    "2024-03-25": "Día de San José", "2024-03-28": "Jueves Santo",
    "2024-03-29": "Viernes Santo", "2024-05-01": "Día del Trabajo",
    "2024-05-13": "Ascensión del Señor", "2024-06-03": "Corpus Christi",
    "2024-06-10": "Sagrado Corazón", "2024-07-01": "San Pedro y San Pablo",
    "2024-07-20": "Día de la Independencia", "2024-08-07": "Batalla de Boyacá",
    "2024-08-19": "Asunción de la Virgen", "2024-10-14": "Día de la Raza",
    "2024-11-04": "Todos los Santos", "2024-11-11": "Independencia de Cartagena",
    "2024-12-08": "Inmaculada Concepción", "2024-12-25": "Navidad",
    "2025-01-01": "Año Nuevo", "2025-01-06": "Día de los Reyes Magos",
    "2025-03-24": "Día de San José", "2025-04-17": "Jueves Santo",
    "2025-04-18": "Viernes Santo", "2025-05-01": "Día del Trabajo",
    "2025-06-02": "Ascensión del Señor", "2025-06-23": "Corpus Christi",
    "2025-06-30": "Sagrado Corazón",
    "2025-07-20": "Día de la Independencia", "2025-08-07": "Batalla de Boyacá",
    "2025-08-18": "Asunción de la Virgen", "2025-10-13": "Día de la Raza",
    "2025-11-03": "Todos los Santos", "2025-11-17": "Independencia de Cartagena",
    "2025-12-08": "Inmaculada Concepción", "2025-12-25": "Navidad",
}

# ── Proveedores sintéticos ─────────────────────────────
PROVEEDORES_SEED = [
    {"codigo": "PROV-001", "razon_social": "Distribuidora Valle S.A.S.", "nit": "900.123.456-7", "ciudad": "Cali", "lead_time_dias": 3, "categorias": ["Abarrotes", "Bebidas"]},
    {"codigo": "PROV-002", "razon_social": "Lácteos del Cauca Ltda.", "nit": "900.234.567-8", "ciudad": "Popayán", "lead_time_dias": 5, "categorias": ["Lácteos", "Huevos"]},
    {"codigo": "PROV-003", "razon_social": "Carnes Premium Colombia S.A.", "nit": "900.345.678-9", "ciudad": "Cali", "lead_time_dias": 4, "categorias": ["Cárnicos", "Avícola"]},
    {"codigo": "PROV-004", "razon_social": "Panadería Industrial El Trigal", "nit": "900.456.789-0", "ciudad": "Palmira", "lead_time_dias": 3, "categorias": ["Panadería", "Delicatessen"]},
    {"codigo": "PROV-005", "razon_social": "Frutos del Pacífico S.A.S.", "nit": "900.567.890-1", "ciudad": "Buenaventura", "lead_time_dias": 7, "categorias": ["Frutas y verduras", "Mariscos"]},
    {"codigo": "PROV-006", "razon_social": "Congelados del Sur Ltda.", "nit": "900.678.901-2", "ciudad": "Cali", "lead_time_dias": 5, "categorias": ["Congelados"]},
    {"codigo": "PROV-007", "razon_social": "Aseo Total de Colombia S.A.", "nit": "900.789.012-3", "ciudad": "Bogotá", "lead_time_dias": 10, "categorias": ["Aseo hogar", "Cuidado personal"]},
    {"codigo": "PROV-008", "razon_social": "Hogar & Estilo S.A.S.", "nit": "900.890.123-4", "ciudad": "Medellín", "lead_time_dias": 12, "categorias": ["Hogar"]},
    {"codigo": "PROV-009", "razon_social": "NutriBebé Colombia S.A.", "nit": "900.901.234-5", "ciudad": "Bogotá", "lead_time_dias": 15, "categorias": ["Bebé"]},
    {"codigo": "PROV-010", "razon_social": "Importadora Andina Ltda.", "nit": "901.012.345-6", "ciudad": "Cali", "lead_time_dias": 8, "categorias": ["Bebidas", "Abarrotes", "Congelados"]},
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
    "Abarrotes": 35, "Bebidas": 25, "Lácteos": 18, "Cárnicos": 15,
    "Panadería": 12, "Congelados": 12, "Frutas y verduras": 20,
    "Avícola": 8, "Mariscos": 6, "Huevos": 5, "Cuidado personal": 15,
    "Aseo hogar": 12, "Hogar": 8, "Delicatessen": 5, "Bebé": 4,
}
