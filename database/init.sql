-- ============================================================
-- InventAI/o — Esquema Estrella (Bodega de Datos)
-- INV-002: Esquema estrella en PostgreSQL
-- INV-60: migrado para el dataset REAL (Siigo, desde 2022) en vez del
-- simulado (Kaggle Favorita, 2013-2017). Cada cambio respecto a la
-- version original queda comentado en su lugar. Detalle completo en
-- docs/INV-60-notas-migracion-dw.md.
-- INV-20: atributos de calendario comercial y de producto (los que usa el
-- modelo de Nivel 1), tabla puente producto_proveedor y la vista
-- dw.v_ventas_diarias_netas. El script es idempotente: sobre una base ya
-- creada, la seccion "Migraciones" agrega lo que falte sin borrar datos.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS app;

-- ============================================================
-- DIMENSIONES
-- ============================================================

-- dim_tiempo
CREATE TABLE IF NOT EXISTS dw.dim_tiempo (
    id_tiempo       SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL UNIQUE,
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    dia             SMALLINT NOT NULL,
    -- INV-60: convencion ISO (1=lunes, 7=domingo), no 0=lunes..6=domingo
    -- como en la version original -- ver docs/INV-60-notas-migracion-dw.md.
    dia_semana      SMALLINT NOT NULL,  -- ISO: 1=lunes, 7=domingo
    nombre_dia      VARCHAR(15) NOT NULL,
    semana_iso      SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    es_fin_semana   BOOLEAN NOT NULL DEFAULT FALSE,
    es_festivo      BOOLEAN NOT NULL DEFAULT FALSE,
    nombre_festivo  VARCHAR(100),
    -- INV-60 (columna nueva): el ETL real ya calculaba este dato por
    -- venta; se sube a dim_tiempo para no perderlo en la migracion.
    es_puente_festivo BOOLEAN NOT NULL DEFAULT FALSE,
    es_quincena     BOOLEAN NOT NULL DEFAULT FALSE,
    temporada       VARCHAR(30),
    -- INV-20: marcas de notebooks/03_calendario_estacionalidad.ipynb, que
    -- usa el factor de calendario del modelo de Nivel 1.
    es_semana_santa BOOLEAN NOT NULL DEFAULT FALSE,
    es_periodo_prima BOOLEAN NOT NULL DEFAULT FALSE,
    bloque_diciembre VARCHAR(20) NOT NULL DEFAULT 'ninguno',
    -- INV-20: el negocio no abre (1 de enero y Viernes Santo). Con esto se
    -- proyectan los dias habiles futuros; los pasados salen de las ventas.
    es_cierre_programado BOOLEAN NOT NULL DEFAULT FALSE
);

-- dim_producto
CREATE TABLE IF NOT EXISTS dw.dim_producto (
    id_producto     SERIAL PRIMARY KEY,
    -- INV-60: INTEGER -> VARCHAR(20). Los codigos reales de Siigo son
    -- alfanumericos (ej. "P841", "P31"), no calzaban en INTEGER.
    codigo_item     VARCHAR(20) NOT NULL UNIQUE,
    nombre          VARCHAR(200) NOT NULL,
    familia         VARCHAR(100) NOT NULL,
    clase           INTEGER,
    categoria       VARCHAR(100) NOT NULL,
    es_perecedero   BOOLEAN NOT NULL DEFAULT FALSE,
    unidad_medida   VARCHAR(20) NOT NULL DEFAULT 'unidad',
    precio_base     NUMERIC(12,2),
    costo_base      NUMERIC(12,2),
    -- INV-20: NUMERIC(5,2) -> (10,2). El margen se deriva de la ultima
    -- venta y hay costos anomalos en Siigo (ej. 02924: costo 1.447.618 vs
    -- precio 22.400 -> -6362.58%) que no cabian y abortaban la carga. Se
    -- carga el dato tal cual; el anomalo queda para revision del negocio.
    margen_pct      NUMERIC(10,2),
    iva_pct         NUMERIC(5,2) NOT NULL DEFAULT 19.00,
    -- INV-20: atributos de la regla de priorizacion (condiciones 1-5 de
    -- notebooks/02_regla_priorizacion.ipynb, features cond1..cond5 del
    -- modelo). Ver etl_real/atributos_producto.py.
    volumen_cm3     NUMERIC(12,2),
    peso_g          NUMERIC(12,2),
    tamano_inferido BOOLEAN NOT NULL DEFAULT FALSE,
    requiere_espacio_bodega BOOLEAN NOT NULL DEFAULT FALSE,
    es_perecedero_estricto BOOLEAN NOT NULL DEFAULT FALSE,
    es_refrigerado  BOOLEAN NOT NULL DEFAULT FALSE,
    rollos_paquete  SMALLINT,
    es_papel_higienico_grande BOOLEAN NOT NULL DEFAULT FALSE,
    es_temporada    BOOLEAN NOT NULL DEFAULT FALSE
);

-- dim_sucursal
CREATE TABLE IF NOT EXISTS dw.dim_sucursal (
    id_sucursal     SERIAL PRIMARY KEY,
    codigo_tienda   INTEGER NOT NULL UNIQUE,
    nombre          VARCHAR(100) NOT NULL,
    -- INV-60: ciudad/departamento ahora nullable. El reporte Siigo no
    -- trae ciudad real por sucursal; la version original inventaba
    -- Cali/Palmira/Tulua (init.sql) que ademas no coincidia con
    -- Centro/Norte/Sur (etl/config.py) -- las dos fuentes originales
    -- del dato sintetico no eran consistentes entre si.
    ciudad          VARCHAR(50),
    departamento    VARCHAR(50),
    tipo            VARCHAR(20) NOT NULL,
    cluster         INTEGER,
    -- INV-60: sin DEFAULT 1.00 forzado -- se calcula del volumen real.
    factor_volumen  NUMERIC(4,2),
    -- INV-20: venta historica total (COP) con la que se calcula factor_volumen.
    volumen_real_cop NUMERIC(16,2)
);

-- dim_proveedor
CREATE TABLE IF NOT EXISTS dw.dim_proveedor (
    id_proveedor    SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) NOT NULL UNIQUE,
    razon_social    VARCHAR(200) NOT NULL,
    nit             VARCHAR(20) NOT NULL,
    ciudad          VARCHAR(50) NOT NULL,
    telefono        VARCHAR(20),
    email           VARCHAR(100),
    lead_time_dias  SMALLINT NOT NULL,
    categorias      TEXT[],
    calificacion    NUMERIC(3,2) DEFAULT 4.00
);

-- dim_evento
CREATE TABLE IF NOT EXISTS dw.dim_evento (
    id_evento       SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,
    tipo            VARCHAR(30) NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     TEXT,
    ambito          VARCHAR(30) NOT NULL DEFAULT 'nacional',
    es_transferido  BOOLEAN NOT NULL DEFAULT FALSE
);

-- producto_proveedor (INV-20): tabla puente que ya generaba
-- etl_real/simular_proveedores.py y no se cargaba.
CREATE TABLE IF NOT EXISTS dw.producto_proveedor (
    id_producto     INTEGER NOT NULL REFERENCES dw.dim_producto(id_producto),
    id_proveedor    INTEGER NOT NULL REFERENCES dw.dim_proveedor(id_proveedor),
    PRIMARY KEY (id_producto, id_proveedor)
);

-- ============================================================
-- TABLAS DE HECHOS
-- ============================================================

-- fact_ventas
CREATE TABLE IF NOT EXISTS dw.fact_ventas (
    id              BIGSERIAL PRIMARY KEY,
    id_producto     INTEGER NOT NULL REFERENCES dw.dim_producto(id_producto),
    id_sucursal     INTEGER NOT NULL REFERENCES dw.dim_sucursal(id_sucursal),
    id_tiempo       INTEGER NOT NULL REFERENCES dw.dim_tiempo(id_tiempo),
    id_proveedor    INTEGER REFERENCES dw.dim_proveedor(id_proveedor),
    cantidad        NUMERIC(12,3) NOT NULL,
    valor_unitario  NUMERIC(12,2) NOT NULL,
    -- NOTA INV-60 (cambio de semantica, no de tipo -- ver
    -- docs/INV-60-notas-migracion-dw.md): en el dato real, valor_total
    -- INCLUYE IVA (verificado: valor_total - valor_iva - costo ==
    -- utilidad reportada por Siigo). En la carga sintetica original,
    -- valor_total era precio de lista SIN IVA. Mismo nombre de columna,
    -- interpretacion distinta segun el origen de la carga.
    valor_total     NUMERIC(14,2) NOT NULL,
    costo_unitario  NUMERIC(12,2) NOT NULL,
    costo_total     NUMERIC(14,2) NOT NULL,
    en_promocion    BOOLEAN NOT NULL DEFAULT FALSE,
    es_devolucion   BOOLEAN NOT NULL DEFAULT FALSE
);

-- fact_inventario
CREATE TABLE IF NOT EXISTS dw.fact_inventario (
    id              BIGSERIAL PRIMARY KEY,
    id_producto     INTEGER NOT NULL REFERENCES dw.dim_producto(id_producto),
    id_sucursal     INTEGER NOT NULL REFERENCES dw.dim_sucursal(id_sucursal),
    id_tiempo       INTEGER NOT NULL REFERENCES dw.dim_tiempo(id_tiempo),
    stock_disponible NUMERIC(12,3) NOT NULL,
    stock_minimo    NUMERIC(12,3) NOT NULL,
    stock_maximo    NUMERIC(12,3) NOT NULL,
    punto_reorden   NUMERIC(12,3) NOT NULL,
    dias_cobertura  NUMERIC(6,1)
);

-- ============================================================
-- SCHEMA APP
-- ============================================================

CREATE TABLE IF NOT EXISTS app.usuarios (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    rol             VARCHAR(30) NOT NULL CHECK (rol IN ('gerente', 'admin_sucursal', 'admin_bodega')),
    id_sucursal     INTEGER REFERENCES dw.dim_sucursal(id_sucursal),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.config_alertas (
    id              SERIAL PRIMARY KEY,
    id_usuario      INTEGER NOT NULL REFERENCES app.usuarios(id),
    tipo_alerta     VARCHAR(50) NOT NULL,
    umbral          NUMERIC(10,2),
    activa          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES OPTIMIZADOS
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_dim_tiempo_fecha ON dw.dim_tiempo(fecha);
CREATE INDEX IF NOT EXISTS idx_dim_tiempo_anio_mes ON dw.dim_tiempo(anio, mes);
CREATE INDEX IF NOT EXISTS idx_dim_producto_familia ON dw.dim_producto(familia);
CREATE INDEX IF NOT EXISTS idx_dim_producto_categoria ON dw.dim_producto(categoria);
CREATE INDEX IF NOT EXISTS idx_dim_evento_fecha ON dw.dim_evento(fecha);
CREATE INDEX IF NOT EXISTS idx_fact_ventas_producto ON dw.fact_ventas(id_producto);
CREATE INDEX IF NOT EXISTS idx_fact_ventas_sucursal ON dw.fact_ventas(id_sucursal);
CREATE INDEX IF NOT EXISTS idx_fact_ventas_tiempo ON dw.fact_ventas(id_tiempo);
CREATE INDEX IF NOT EXISTS idx_fact_ventas_compuesto ON dw.fact_ventas(id_sucursal, id_tiempo, id_producto);
CREATE INDEX IF NOT EXISTS idx_fact_inventario_compuesto ON dw.fact_inventario(id_sucursal, id_tiempo, id_producto);
-- INV-20: historia de un par producto x sucursal (consulta del servicio de prediccion)
CREATE INDEX IF NOT EXISTS idx_fact_ventas_par ON dw.fact_ventas(id_producto, id_sucursal, id_tiempo);

-- ============================================================
-- MIGRACIONES (INV-20) -- sobre una base creada con una version
-- anterior de este script, CREATE TABLE IF NOT EXISTS no agrega
-- columnas: estas sentencias si, sin tocar los datos existentes.
-- ============================================================

ALTER TABLE dw.dim_tiempo ADD COLUMN IF NOT EXISTS es_semana_santa BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_tiempo ADD COLUMN IF NOT EXISTS es_periodo_prima BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_tiempo ADD COLUMN IF NOT EXISTS bloque_diciembre VARCHAR(20) NOT NULL DEFAULT 'ninguno';
ALTER TABLE dw.dim_tiempo ADD COLUMN IF NOT EXISTS es_cierre_programado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS volumen_cm3 NUMERIC(12,2);
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS peso_g NUMERIC(12,2);
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS tamano_inferido BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS requiere_espacio_bodega BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS es_perecedero_estricto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS es_refrigerado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS rollos_paquete SMALLINT;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS es_papel_higienico_grande BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_producto ADD COLUMN IF NOT EXISTS es_temporada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dw.dim_sucursal ADD COLUMN IF NOT EXISTS volumen_real_cop NUMERIC(16,2);
ALTER TABLE dw.dim_producto ALTER COLUMN margen_pct TYPE NUMERIC(10,2);

-- ============================================================
-- VISTAS (INV-20)
-- ============================================================

-- Venta diaria neta por producto x sucursal: sin devoluciones y solo
-- cantidades positivas, la misma regla del panel diario de
-- notebooks/01_calidad_y_panel.ipynb con el que se entrenaron los modelos.
-- tipo_sucursal permite quedarse con las sucursales fisicas
-- ('principal', 'estandar'), como hace ese panel.
CREATE OR REPLACE VIEW dw.v_ventas_diarias_netas AS
SELECT p.codigo_item,
       s.nombre AS sucursal,
       s.tipo   AS tipo_sucursal,
       t.fecha,
       SUM(v.cantidad)    AS unidades,
       SUM(v.valor_total) AS valor
FROM dw.fact_ventas v
JOIN dw.dim_producto p ON p.id_producto = v.id_producto
JOIN dw.dim_sucursal s ON s.id_sucursal = v.id_sucursal
JOIN dw.dim_tiempo   t ON t.id_tiempo   = v.id_tiempo
WHERE NOT v.es_devolucion AND v.cantidad > 0
GROUP BY p.codigo_item, s.nombre, s.tipo, t.fecha;

-- ============================================================
-- INV-60: sin INSERT seed de dim_sucursal aqui (a proposito).
-- Las sucursales reales (PRINCIPAL, LA 21, GLORIETA, SIN_SUCURSAL y, desde
-- INV-61, BODEGA_CENTRAL) las
-- carga etl_real/cargar_postgres.py desde
-- data/processed_real/dim_sucursal.csv -- ver
-- docs/INV-60-tutorial-migracion.md.
-- ============================================================