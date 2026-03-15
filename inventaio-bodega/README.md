# InventAI/o — Bodega de Datos (INV-002 + INV-003)

Pipeline ETL para construir el esquema estrella de InventAI/o usando datos reales
de Corporación Favorita (Kaggle) + datos sintéticos complementarios.

## Requisitos previos

- Docker y Docker Compose
- Python 3.11+
- Cuenta de Kaggle (para descargar el dataset)
- ~2 GB de espacio en disco

## Guía paso a paso

### Paso 0: Clonar y preparar el entorno

```bash
# Ir al directorio del proyecto
cd inventaio-bodega

# Copiar variables de entorno
cp .env.example .env

# Crear entorno virtual de Python
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 1: Levantar PostgreSQL y Redis con Docker

```bash
docker compose up -d

# Verificar que los contenedores estén saludables
docker compose ps

# Esperado:
# inventaio-db     running (healthy)
# inventaio-redis  running (healthy)
```

El script `database/init.sql` se ejecuta automáticamente al crear el contenedor
y crea los schemas `dw` y `app` con todas las tablas, índices y restricciones.

### Paso 2: Descargar datos de Kaggle

Ve a https://www.kaggle.com/c/favorita-grocery-sales-forecasting/data

Descarga estos archivos y colócalos en `data/raw/`:

```
data/raw/
├── train.csv           (~5 GB, ~125M filas)
├── items.csv
├── stores.csv
├── holidays_events.csv
└── transactions.csv    (opcional)
```

**Alternativa con API de Kaggle:**
```bash
pip install kaggle
# Configura tu API key en ~/.kaggle/kaggle.json
kaggle competitions download -c favorita-grocery-sales-forecasting -p data/raw/
cd data/raw && unzip favorita-grocery-sales-forecasting.zip
```

### Paso 3: Ejecutar el pipeline ETL

El pipeline tiene 3 scripts que se ejecutan en secuencia:

```bash
cd etl

# Paso 1: Transformar datos de Favorita
# - Filtra 3 tiendas y ~200 productos
# - Aplica factor de escala (Sucursal Principal = 5x)
# - Recorta a 730 días
python 01_transform_favorita.py

# Paso 2: Generar datos sintéticos
# - Precios y costos por categoría (COP)
# - 10 proveedores con lead times
# - Inventario diario coherente con ventas
# - Dimensión tiempo con festivos colombianos
python 02_generate_synthetic.py

# Paso 3: Cargar al esquema estrella
# - Carga idempotente (TRUNCATE + INSERT)
# - Dimensiones → Hechos → Usuarios seed
python 03_load_warehouse.py
```

### Paso 4: Validar la bodega

```bash
python validate.py
```

Resultado esperado:
```
✅ Todos los datos pasaron la validación
✅ Bodega de datos validada exitosamente
```

### Paso 5: Verificar manualmente (opcional)

```bash
# Conectarse a PostgreSQL
docker exec -it inventaio-db psql -U inventaio_user -d inventaio

# Consultas de verificación
SELECT COUNT(*) FROM dw.fact_ventas;
SELECT COUNT(*) FROM dw.fact_inventario;

-- Ventas por sucursal
SELECT s.nombre, COUNT(*), ROUND(SUM(fv.valor_total)::numeric, 0) AS total_cop
FROM dw.fact_ventas fv
JOIN dw.dim_sucursal s ON fv.id_sucursal = s.id_sucursal
GROUP BY s.nombre ORDER BY total_cop DESC;

-- Productos por categoría
SELECT categoria, COUNT(*) FROM dw.dim_producto GROUP BY categoria ORDER BY count DESC;

-- Festivos cargados
SELECT * FROM dw.dim_tiempo WHERE es_festivo = TRUE LIMIT 10;

-- Stock actual por sucursal (último día)
SELECT s.nombre, COUNT(*), ROUND(AVG(fi.stock_disponible)::numeric, 0) AS avg_stock
FROM dw.fact_inventario fi
JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
WHERE t.fecha = (SELECT MAX(fecha) FROM dw.dim_tiempo)
GROUP BY s.nombre;
```

## Estructura del proyecto

```
inventaio-bodega/
├── docker-compose.yml          # PostgreSQL 16 + Redis 7
├── .env.example                # Variables de entorno
├── requirements.txt            # Dependencias Python
├── database/
│   └── init.sql                # DDL: schemas, tablas, índices
├── etl/
│   ├── config.py               # Configuración, mapeos, constantes
│   ├── 01_transform_favorita.py  # Filtrar y adaptar datos Favorita
│   ├── 02_generate_synthetic.py  # Generar precios, proveedores, inventario
│   ├── 03_load_warehouse.py      # Cargar al esquema estrella
│   └── validate.py               # Validación de calidad
├── data/
│   ├── raw/                    # CSVs de Kaggle (no versionados)
│   └── processed/              # Parquets intermedios
└── README.md
```

## Esquema estrella

```
                    ┌──────────────┐
                    │ dim_tiempo   │
                    │ (festivos,   │
                    │  quincenas,  │
                    │  temporadas) │
                    └──────┬───────┘
                           │
┌──────────────┐   ┌──────┴───────┐   ┌──────────────┐
│ dim_producto │───│ fact_ventas  │───│ dim_sucursal │
│ (15 categ.,  │   │ (~500K+ reg) │   │ (Principal,  │
│  200 prods)  │   └──────┬───────┘   │  Norte, Sur) │
└──────────────┘          │           └──────────────┘
                          │
┌──────────────┐   ┌──────┴───────┐
│ dim_proveedor│───│fact_inventario│
│ (10 proveed.)│   │ (stock diario)│
└──────────────┘   └──────────────┘
```

## Sucursales

| Sucursal           | Factor | Ventas esperadas |
|--------------------|--------|------------------|
| Sucursal Principal | 5.0x   | ~70% del total   |
| Sucursal Norte     | 1.0x   | ~15% del total   |
| Sucursal Sur       | 1.0x   | ~15% del total   |

## Notas importantes

- **Reproducibilidad**: Todo el pipeline usa `--seed 42`
- **Idempotencia**: Ejecutar el paso 3 múltiples veces produce el mismo resultado
- **Rendimiento**: El paso 1 puede tomar 5-15 min dependiendo de tu máquina (lee ~5 GB)
- **Datos reales vs sintéticos**: Las ventas son de Favorita (reales), los precios/proveedores/inventario son sintéticos
- **Contexto colombiano**: Festivos 2023-2025, quincenas, temporadas, precios en COP
