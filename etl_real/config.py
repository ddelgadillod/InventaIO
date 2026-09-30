"""
INV-60 — Configuración compartida del pipeline de construcción del DW real.

Reemplaza el dataset simulado (Kaggle Favorita 2013-2017) que hoy carga
InventaIO por el dataset real producido por el repo ventas2 (ETL de
ventas POS Siigo, 2023-2025). Ver docs/INV-60-compatibilidad-datos.md y
docs/INV-60-notas-migracion-dw.md.

Este pipeline vive en InventaIO pero NO importa código de ventas2 en
tiempo de ejecución (ver etl_real/calendario_utils.py) -- los insumos de
entrada (ventas_tidy.csv, terminal_sucursal.csv y el inventario físico)
son artefactos que ese otro repo produce; aquí solo se leen desde
data/raw_real/ (o la ruta que indiquen las variables de entorno de
abajo). Ver etl_real/README.md para cómo llevarlos ahí. Los festivos se
versionan en este directorio (INV-20, ver generar_festivos.py).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_REAL = BASE_DIR / "data" / "raw_real"

VENTAS_TIDY_CSV = Path(os.environ.get("VENTAS_TIDY_CSV", DATA_RAW_REAL / "ventas_tidy.csv"))
# INV-20: los festivos se versionan en este directorio (datos públicos, no
# del negocio) y cubren hasta 2027 -- dim_tiempo debe llegar más allá de la
# última venta para que el servicio de predicción arme la ventana de los
# próximos días hábiles. Ver generar_festivos.py.
FESTIVOS_CSV = Path(os.environ.get(
    "FESTIVOS_CSV", Path(__file__).resolve().parent / "festivos_colombia_2022_2027.csv"
))
TERMINAL_SUCURSAL_CSV = Path(os.environ.get("TERMINAL_SUCURSAL_CSV", DATA_RAW_REAL / "terminal_sucursal.csv"))
# INV-61 -- inventario físico real (corte 2025-12-31), mismo patrón de
# variable de entorno + default bajo DATA_RAW_REAL que los tres insumos
# de arriba (no BASE_DIR/"inventario", esa era la convención de ventas2).
INVENTARIO_XLSX = Path(os.environ.get(
    "INVENTARIO_XLSX", DATA_RAW_REAL / "inventario" / "inventarioooo.xlsx"
))

# Distinto de data/processed/ (que usa el pipeline Favorita/etl/) para
# no mezclar los dos datasets en el mismo directorio de salida.
SALIDA_DIR = BASE_DIR / "data" / "processed_real"

CATEGORIA_MANUAL_OVERRIDE_CSV = Path(__file__).resolve().parent / "categoria_manual_override.csv"
CORRECCION_HEURISTICA_CSV = Path(__file__).resolve().parent / "correccion_heuristica.csv"
PRODUCTOS_EXCLUIDOS_CSV = Path(__file__).resolve().parent / "productos_excluidos.csv"
# INV-22 -- correcciones del negocio a las marcas de logística de
# dim_producto (requiere_frio, se_vende_por_kilo). Mandan sobre la regla.
OVERRIDES_REQUIERE_FRIO_CSV = Path(__file__).resolve().parent / "overrides_requiere_frio.csv"
OVERRIDES_POR_KILO_CSV = Path(__file__).resolve().parent / "overrides_por_kilo.csv"

RANDOM_SEED = 42  # mismo valor que usa InventaIO, por consistencia documental

# ── Sucursales ──────────────────────────────────────────────────────
# Nombres reales (crosswalk terminal_pos->sucursal de INV-61), no los
# ficticios de InventaIO (Sucursal Principal/Norte/Sur). Se agrega
# SIN_SUCURSAL como sucursal placeholder (no física) para que las ventas
# de terminal FV2 (facturación electrónica sin punto de venta) tengan un
# FK válido en fact_ventas sin descartarlas en silencio.
SUCURSALES_REALES = ["PRINCIPAL", "LA 21", "GLORIETA"]
SUCURSAL_SIN_TERMINAL = "SIN_SUCURSAL"

# ── Categorías objetivo ────────────────────────────────────────────────
# Taxonomía real, resultado de la revisión manual del catálogo completo
# (ver categoria_manual_override.csv y docs/INV-60-notas-migracion-dw.md).
# Reemplaza las 15 categorías genéricas heredadas de InventaIO/Favorita --
# esas dejaban el 60% del catálogo real en el default "Abarrotes" porque
# el negocio vende mucho más que abarrotes de supermercado genérico.
# "Delicatessen" se retira (nunca tuvo ninguna regla de match real).
# "Otros" es nueva: para cargos que no son mercancía (ej. impuesto a la
# bolsa), no para productos mal clasificados.
CATEGORIAS_OBJETIVO = [
    "Abarrotes", "Aseo hogar", "Cuidado personal", "Bebidas", "Confitería",
    "Lácteos", "Hogar", "Panadería", "Frutas y verduras", "Condimentos",
    "Cárnicos", "Salsas y aderezos", "Aceites y sustitutos", "Mascotas",
    "Chocolate", "Semillas y frutos secos", "Café y sustitutos", "Cereales",
    "Mariscos", "Medicamentos", "Arroz", "Bebé", "Conservas",
    "Azúcares y endulzantes", "Harinas", "Licores", "Repostería",
    "Avícola", "Anchetas", "Granos", "Congelados", "Bebidas instantáneas",
    "Velas y velones", "Huevos", "Otros",
]

CATEGORIAS_PERECEDERAS = [
    "Frutas y verduras", "Huevos", "Cárnicos", "Avícola", "Mariscos", "Lácteos",
]

# ── Atributos de producto para priorización y modelado (INV-20) ─────────
# Reglas de las condiciones 1-5 de notebooks/02_regla_priorizacion.ipynb,
# llevadas a dim_producto para que el servicio de predicción y los demás
# módulos lean los mismos atributos con los que se entrenó el modelo.
# Mismos valores que PARAMS en notebooks/common_priorizacion.py.
UMBRAL_VOLUMEN_CM3 = 3000               # condición 1 (dado por el negocio)
UMBRAL_PESO_G = 3000                    # condición 1 (dado por el negocio)
UMBRAL_ROLLOS_PAPEL_HIGIENICO = 18      # condición 4 (dado por el negocio)
UMBRAL_NUMERO_SUELTO_INFERENCIA = 50    # "*500" sin unidad -> tamaño inferido
CATEGORIAS_PERECEDERAS_ESTRICTO = ["Frutas y verduras", "Huevos"]              # condición 2
CATEGORIAS_REFRIGERADAS = ["Lácteos", "Avícola", "Mariscos", "Cárnicos"]       # condición 3

# ── Marcas de logística (INV-22) ─────────────────────────────────────────
# No son features del modelo: las usa la recomendación de transferencias.
# requiere_frio = es_refrigerado (condición 3, por categoría) salvo que el
# nombre indique un producto estable a temperatura ambiente. Se compara por
# palabra completa, en singular o plural. Las cinco primeras son la lista
# inicial acordada; las demás salen de revisar los 429 refrigerados por
# categoría, empezando por los que ya se guardan en la Bodega (que no tiene
# frío). Es la regla inicial: el negocio la corrige en
# OVERRIDES_REQUIERE_FRIO_CSV.
PALABRAS_PRODUCTO_ESTABLE = [
    "ATUN", "SARDINA", "EN POLVO", "CALDO", "RICOSTILLA",       # lista inicial acordada
    "LATA", "VIENA", "ANTIPASTO", "FRANKFURT", "LECHE DE COCO",  # enlatados
    "TETRA", "CAJA",                                            # leche y bebidas larga vida
    "KLIM", "NESTOGENO", "FORTI", "FORTILECHE", "PROLECHE",     # leche en polvo
    "RODEO", "TONING",
    "LECHERA", "CONDEN",                                        # leche condensada
    "SALS", "SALSA", "MAGNESIA",                                # salsas y la leche de magnesia
    "PAPA MARGARITA", "CHIDOS", "CONO", "ARROZ CON LECHE", "MACARRON",  # pasabocas y mezclas secas
    "COLCAFE", "CAFE CON LECHE", "COBERTURA",                   # café instantáneo y repostería
]
# INV-21: categorías que requieren frío aunque la condición 3 del modelo no
# las cuente como refrigeradas (es_refrigerado no cambia: es feature del
# modelo). Aquí no se aplican las palabras de producto estable -- "HELADO
# CONO" es un helado --; lo que no necesita frío va a los overrides (P431).
CATEGORIAS_FRIO_ADICIONALES = ["Congelados"]
# se_vende_por_kilo: la mitad o más de sus líneas de venta (cantidad > 0)
# tienen decimales. En 2022-2025 la separación es limpia: 63 productos pasan
# del 90 % y 119 no llegan al 10 %.
UMBRAL_FRACCION_LINEAS_KILO = 0.5

# ── Calendario comercial (INV-20) ───────────────────────────────────────
# Rango de dim_tiempo: desde la primera venta hasta FECHA_FIN_CALENDARIO (o
# la última venta, si es posterior). Debe quedar cubierto por FESTIVOS_CSV.
FECHA_FIN_CALENDARIO = "2027-12-31"
# Bloques y periodos de notebooks/03_calendario_estacionalidad.ipynb (mismos
# valores que PARAMS en notebooks/common_priorizacion.py).
DICIEMBRE_NOVENA = (16, 23)
DICIEMBRE_NOCHEBUENA_NAVIDAD = (24, 25)
DICIEMBRE_FIN_DE_ANIO = (30, 31)
ENERO_POSTNAVIDAD_MAX_DIA = 6
PERIODO_PRIMA_JUNIO = (10, 30)
PERIODO_PRIMA_DICIEMBRE = (1, 20)
SEMANA_SANTA_DIAS_ANTES_JUEVES = 3      # ventana [Jueves Santo - 3, Jueves Santo + 4]
SEMANA_SANTA_DIAS_DESPUES_JUEVES = 4
# Días en que el negocio no abre, confirmados por el negocio (2026-09-29): en
# 2022-2025 no hubo ventas ningún 1 de enero ni ningún Viernes Santo. Los otros
# tres días sin venta de la historia (2023-04-23, 2024-09-29, 2025-09-27) se
# tratan como anomalías, no como cierres programados.
FESTIVOS_CIERRE = ["Año Nuevo", "Viernes Santo"]

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
                            "COLIFLOR", "ARVEJA", "YUCA", "MAIZ PETO",
                            "REPOLLO", "PEPINO", "CILANTRO", "PIMENTON"]),
    ("Bebé", ["PAÑAL", "BEBE", "FORMULA INFANTIL", "TOALLITA HUMEDA",
              "NUTRIBEN", "PAÑITOS HUMEDOS", "TOALLITA HUGGIES"]),
    ("Cuidado personal", ["SHAMPOO", "CHAMPU", "CHAMP ", "JABON DE TOCADOR",
                           "JAB PROTEX", "DESOD", "CREMA DENTAL", "CREMA DENT",
                           "COLGATE", "PANTENE", "PROTECTOR", "TOALLA HIGIENICA",
                           "TOALLA NOSOTRAS", "TOALLA KOTEX", "PROTECTORES NOSOTRAS",
                           "AFEITAR", "CEPILLO DENTAL", "CEPILLO DENT",
                           "ENJUAGUE BUCAL", "CREMA PEINAR"]),
    ("Aseo hogar", ["DET ", "DETERGENTE", "JABON EN POLVO", "JABON LOZA",
                     "LAVALOZA", "PAPEL HIG", "LIMPIA", "CLORO", "AMBIENTAL",
                     "ESCOBA", "TRAPERO", "FAB ", "ARIEL", "BLANCOX",
                     "SUAVITEL", "VARSOL", "ESPONJA", "ESPONJILLA", "SCOTCH BRITE",
                     "TOALLA COCINA", "VANISH", "DESENGRASANTE", "CERA "]),
    ("Bebidas", ["CERVEZA", "GASEOSA", "JUGO", "AGUA", "MALTA", "VINO",
                 "WHISKY", "AGUARDIENTE", "RON ", "CAFE", "BEBIDA",
                 "REFRESCO", "POLA ", "COLA ", "TE HELADO", "ELECTROLIT",
                 "GATORADE"]),
    ("Hogar", ["VELA", "VASO", "OLLA", "SARTEN", "COBIJA", "BOMBILLO",
               "PILA ", "BATERIA"]),
]
DEFAULT_CATEGORIA = "Abarrotes"  # mismo fallback que usa InventaIO

UNIDAD_MEDIDA_PATTERNS = [
    # (?<![A-Za-z]) en vez de \b al inicio: \b no marca límite entre un
    # dígito y una letra (ambos son \w), así que "*500GR" pegado (sin
    # espacio) nunca hacía match con el \b original -- solo "500 GR" con
    # espacio. Encontrado por tests/test_etl_real.py. El dígito antes de
    # la unidad es el caso más común en el catálogo real, no la excepción.
    ("kg", r"(?<![A-Za-z])K\.?G\.?S?\b|\bKILO"),
    ("g", r"(?<![A-Za-z])G\.?R?\.?S?\b(?!\w)"),
    ("l", r"(?<![A-Za-z])L\.?T\.?S?\b|\bLITRO"),
    ("ml", r"(?<![A-Za-z])M\.?L\.?S?\b"),
    ("un", r"(?<![A-Za-z])UN\.?D?\.?S?\b|\bUNIDAD"),
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
    {"codigo": "PROV-004", "razon_social": "Panadería Industrial El Trigal", "nit": "900.456.789-0", "ciudad": "Bogotá", "lead_time_dias": 3, "categorias": ["Panadería", "Repostería"]},
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
