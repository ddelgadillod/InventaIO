-- ============================================================
-- InventAI/o - Inicialización de base de datos
-- Schemas: dw (data warehouse), app (aplicación)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS app;

-- ============================================================
-- DIMENSIONES
-- ============================================================

CREATE TABLE dw.dim_tiempo (
    id_tiempo       SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL UNIQUE,
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    dia             SMALLINT NOT NULL,
    dia_semana      SMALLINT NOT NULL,       -- 0=Lunes, 6=Domingo
    nombre_dia      VARCHAR(15) NOT NULL,
    semana_iso      SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    es_fin_semana   BOOLEAN NOT NULL DEFAULT FALSE,
    es_festivo      BOOLEAN NOT NULL DEFAULT FALSE,
    nombre_festivo  VARCHAR(100),
    es_quincena     BOOLEAN NOT NULL DEFAULT FALSE,  -- día 15 o último del mes
    temporada       VARCHAR(30)              -- navidad, escolar, etc.
);

CREATE TABLE dw.dim_producto (
    id_producto     SERIAL PRIMARY KEY,
    codigo_item     INTEGER NOT NULL UNIQUE,  -- item_nbr original de Favorita
    nombre          VARCHAR(200) NOT NULL,
    familia         VARCHAR(100) NOT NULL,     -- family de Favorita
    clase           INTEGER,                   -- class de Favorita
    categoria       VARCHAR(100) NOT NULL,     -- agrupación para InventAI/o (15 categorías)
    es_perecedero   BOOLEAN NOT NULL DEFAULT FALSE,
    unidad_medida   VARCHAR(20) NOT NULL DEFAULT 'unidad',
    precio_base     NUMERIC(12,2),
    costo_base      NUMERIC(12,2),
    margen_pct      NUMERIC(5,2)
);

CREATE TABLE dw.dim_sucursal (
    id_sucursal     SERIAL PRIMARY KEY,
    codigo_tienda   INTEGER NOT NULL UNIQUE,  -- store_nbr original
    nombre          VARCHAR(100) NOT NULL,
    ciudad          VARCHAR(100) NOT NULL,
    departamento    VARCHAR(100) NOT NULL DEFAULT 'Valle del Cauca',
    tipo            VARCHAR(50) NOT NULL,      -- principal, secundaria
    cluster         INTEGER,
    factor_escala   NUMERIC(3,1) NOT NULL DEFAULT 1.0  -- 5.0 para principal, 1.0 para las demás
);

CREATE TABLE dw.dim_proveedor (
    id_proveedor    SERIAL PRIMARY KEY,
    nit             VARCHAR(20) NOT NULL UNIQUE,
    razon_social    VARCHAR(200) NOT NULL,
    contacto        VARCHAR(200),
    telefono        VARCHAR(20),
    ciudad          VARCHAR(100),
    lead_time_dias  SMALLINT NOT NULL,        -- 3-15 días
    categorias      TEXT[]                     -- array de categorías que surte
);

CREATE TABLE dw.dim_evento (
    id_evento       SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,
    tipo_evento     VARCHAR(50) NOT NULL,      -- festivo, quincena, temporada, promocion
    nombre          VARCHAR(200) NOT NULL,
    ambito          VARCHAR(50) NOT NULL DEFAULT 'nacional',  -- nacional, regional, local
    es_transferido  BOOLEAN NOT NULL DEFAULT FALSE
);

-- ============================================================
-- TABLAS DE HECHOS
-- ============================================================

CREATE TABLE dw.fact_ventas (
    id              BIGSERIAL PRIMARY KEY,
    id_producto     INTEGER NOT NULL REFERENCES dw.dim_producto(id_producto),
    id_sucursal     INTEGER NOT NULL REFERENCES dw.dim_sucursal(id_sucursal),
    id_tiempo       INTEGER NOT NULL REFERENCES dw.dim_tiempo(id_tiempo),
    id_proveedor    INTEGER REFERENCES dw.dim_proveedor(id_proveedor),
    cantidad        NUMERIC(12,2) NOT NULL,
    valor_unitario  NUMERIC(12,2) NOT NULL,
    valor_total     NUMERIC(14,2) NOT NULL,
    costo_unitario  NUMERIC(12,2) NOT NULL,
    costo_total     NUMERIC(14,2) NOT NULL,
    en_promocion    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE dw.fact_inventario (
    id              BIGSERIAL PRIMARY KEY,
    id_producto     INTEGER NOT NULL REFERENCES dw.dim_producto(id_producto),
    id_sucursal     INTEGER NOT NULL REFERENCES dw.dim_sucursal(id_sucursal),
    id_tiempo       INTEGER NOT NULL REFERENCES dw.dim_tiempo(id_tiempo),
    stock_disponible NUMERIC(12,2) NOT NULL,
    stock_minimo    NUMERIC(12,2) NOT NULL,
    stock_maximo    NUMERIC(12,2) NOT NULL,
    punto_reorden   NUMERIC(12,2) NOT NULL
);

-- ============================================================
-- TABLAS APP
-- ============================================================

CREATE TABLE app.usuarios (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(200) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nombre          VARCHAR(200) NOT NULL,
    rol             VARCHAR(30) NOT NULL CHECK (rol IN ('gerente', 'admin_sucursal', 'admin_bodega')),
    id_sucursal     INTEGER REFERENCES dw.dim_sucursal(id_sucursal),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE app.config_alertas (
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

CREATE INDEX idx_fact_ventas_tiempo ON dw.fact_ventas(id_tiempo);
CREATE INDEX idx_fact_ventas_producto ON dw.fact_ventas(id_producto);
CREATE INDEX idx_fact_ventas_sucursal ON dw.fact_ventas(id_sucursal);
CREATE INDEX idx_fact_ventas_compuesto ON dw.fact_ventas(id_sucursal, id_producto, id_tiempo);

CREATE INDEX idx_fact_inventario_tiempo ON dw.fact_inventario(id_tiempo);
CREATE INDEX idx_fact_inventario_producto ON dw.fact_inventario(id_producto);
CREATE INDEX idx_fact_inventario_sucursal ON dw.fact_inventario(id_sucursal);
CREATE INDEX idx_fact_inventario_compuesto ON dw.fact_inventario(id_sucursal, id_producto, id_tiempo);

CREATE INDEX idx_dim_tiempo_fecha ON dw.dim_tiempo(fecha);
CREATE INDEX idx_dim_producto_categoria ON dw.dim_producto(categoria);
CREATE INDEX idx_dim_producto_familia ON dw.dim_producto(familia);
