-- ============================================================
-- InventAI/o — Esquema Estrella (Bodega de Datos)
-- INV-002: Esquema estrella en PostgreSQL
-- INV-60: migrado para el dataset REAL (Siigo, 2023-2025) en vez del
-- simulado (Kaggle Favorita, 2013-2017). Cada cambio respecto a la
-- version original queda comentado en su lugar. Detalle completo en
-- docs/INV-60-notas-migracion-dw.md.
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
    temporada       VARCHAR(30)
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
    margen_pct      NUMERIC(5,2),
    iva_pct         NUMERIC(5,2) NOT NULL DEFAULT 19.00
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
    factor_volumen  NUMERIC(4,2)
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

-- ============================================================
-- INV-60: sin INSERT seed de dim_sucursal aqui (a proposito).
-- Las sucursales reales (PRINCIPAL, LA 21, GLORIETA, SIN_SUCURSAL) las
-- carga etl_real/cargar_postgres.py desde
-- data/processed_real/dim_sucursal.csv -- ver
-- docs/INV-60-tutorial-migracion.md.
-- ============================================================