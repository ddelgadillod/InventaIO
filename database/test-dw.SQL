-- ============================================================
-- InventAI/o — Script de verificación de bodega de datos
-- Ejecutar después del pipeline ETL para capturar evidencia
-- Uso: docker-compose.exe exec postgres psql -U inventaio_user -d inventaio -f /path/to/verify.sql
-- ============================================================

\echo '============================================================'
\echo 'INVENTAIO - REPORTE DE VERIFICACION DE BODEGA DE DATOS'
\echo 'Fecha de ejecucion:' :DBNAME
\echo '============================================================'
\pset border 2
\timing on

-- ============================================================
-- INV-002 CA1: Diagrama ER documentado
-- Verificación: Todas las tablas existen con relaciones correctas
-- ============================================================
\echo ''
\echo '>>> INV-002 CA1: Tablas y columnas del esquema estrella'
SELECT table_schema, table_name,
       (SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) as columnas
FROM information_schema.tables t
WHERE table_schema IN ('dw', 'app')
ORDER BY table_schema, table_name;

-- ============================================================
-- INV-002 CA2: fact_ventas con columnas especificadas
-- ============================================================
\echo ''
\echo '>>> INV-002 CA2: Columnas de fact_ventas'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'dw' AND table_name = 'fact_ventas'
ORDER BY ordinal_position;

-- ============================================================
-- INV-002 CA3: fact_inventario con columnas especificadas
-- ============================================================
\echo ''
\echo '>>> INV-002 CA3: Columnas de fact_inventario'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'dw' AND table_name = 'fact_inventario'
ORDER BY ordinal_position;

-- ============================================================
-- INV-002 CA4: 5 dimensiones implementadas
-- ============================================================
\echo ''
\echo '>>> INV-002 CA4: Dimensiones implementadas'
SELECT table_name, 
       (SELECT COUNT(*) FROM information_schema.columns c 
        WHERE c.table_schema = 'dw' AND c.table_name = t.table_name) as columnas
FROM information_schema.tables t
WHERE table_schema = 'dw' AND table_name LIKE 'dim_%'
ORDER BY table_name;

-- ============================================================
-- INV-002 CA5: dim_tiempo con festivos, quincenas, temporadas
-- ============================================================
\echo ''
\echo '>>> INV-002 CA5: dim_tiempo - festivos, quincenas, temporadas'
SELECT 
    COUNT(*) as total_dias,
    MIN(fecha) as fecha_inicio,
    MAX(fecha) as fecha_fin,
    COUNT(*) FILTER (WHERE es_festivo) as festivos,
    COUNT(*) FILTER (WHERE es_quincena) as quincenas,
    COUNT(DISTINCT temporada) as temporadas_distintas
FROM dw.dim_tiempo;

\echo ''
\echo '>>> INV-002 CA5: Detalle de temporadas'
SELECT temporada, COUNT(*) as dias
FROM dw.dim_tiempo GROUP BY temporada ORDER BY dias DESC;

\echo ''
\echo '>>> INV-002 CA5: Festivos por año'
SELECT anio, COUNT(*) as festivos
FROM dw.dim_tiempo WHERE es_festivo
GROUP BY anio ORDER BY anio;

\echo ''
\echo '>>> INV-002 CA5: Muestra festivos 2017'
SELECT fecha, nombre_festivo
FROM dw.dim_tiempo WHERE es_festivo AND anio = 2017
ORDER BY fecha;

-- ============================================================
-- INV-002 CA6/CA9: Migraciones ejecutables (init.sql)
-- Verificación: schemas y tablas creados sin errores
-- ============================================================
\echo ''
\echo '>>> INV-002 CA6: Schemas creados'
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('dw', 'app');

-- ============================================================
-- INV-002 CA7: Índices optimizados
-- ============================================================
\echo ''
\echo '>>> INV-002 CA7: Indices del schema dw'
SELECT indexname, tablename
FROM pg_indexes WHERE schemaname = 'dw'
ORDER BY tablename, indexname;

-- ============================================================
-- INV-002 CA9: Tablas app (usuarios, config_alertas)
-- ============================================================
\echo ''
\echo '>>> INV-002 CA9: Tablas del schema app'
SELECT table_name,
       (SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_schema = 'app' AND c.table_name = t.table_name) as columnas
FROM information_schema.tables t
WHERE table_schema = 'app' ORDER BY table_name;

\echo ''
\echo '>>> INV-002 CA9: Constraint de rol en usuarios'
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'app.usuarios'::regclass AND contype = 'c';

-- ============================================================
-- INV-003 CA1: 200+ productos en 15 categorías
-- ============================================================
\echo ''
\echo '>>> INV-003 CA1: Productos por categoría'
SELECT categoria, COUNT(*) as productos,
       ROUND(AVG(precio_base)::numeric, 0) as precio_prom_cop,
       ROUND(AVG(margen_pct)::numeric, 1) as margen_prom,
       ROUND(AVG(iva_pct)::numeric, 0) as iva
FROM dw.dim_producto
GROUP BY categoria ORDER BY productos DESC;

SELECT COUNT(*) as total_productos, COUNT(DISTINCT categoria) as total_categorias
FROM dw.dim_producto;

-- ============================================================
-- INV-003 CA2: 3 sucursales (Cali, Palmira, Tuluá)
-- ============================================================
\echo ''
\echo '>>> INV-003 CA2: Sucursales'
SELECT codigo_tienda, nombre, ciudad, departamento, tipo, factor_volumen
FROM dw.dim_sucursal ORDER BY codigo_tienda;

-- ============================================================
-- INV-003 CA3: 10 proveedores con lead times 3-15 días
-- ============================================================
\echo ''
\echo '>>> INV-003 CA3: Proveedores'
SELECT codigo, razon_social, ciudad, lead_time_dias, categorias
FROM dw.dim_proveedor ORDER BY codigo;

SELECT COUNT(*) as total,
       MIN(lead_time_dias) as min_lead_time,
       MAX(lead_time_dias) as max_lead_time
FROM dw.dim_proveedor;

-- ============================================================
-- INV-003 CA4: 730+ días de ventas con estacionalidad
-- ============================================================
\echo ''
\echo '>>> INV-003 CA4: Rango temporal de ventas'
SELECT MIN(t.fecha) as primera_venta,
       MAX(t.fecha) as ultima_venta,
       COUNT(DISTINCT t.fecha) as dias_con_ventas,
       MAX(t.fecha) - MIN(t.fecha) as rango_dias
FROM dw.fact_ventas v
JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo;

-- ============================================================
-- INV-003 CA5: Inventario diario coherente con ventas
-- ============================================================
\echo ''
\echo '>>> INV-003 CA5: Inventario - coherencia'
SELECT 
    COUNT(*) as total_registros,
    COUNT(*) FILTER (WHERE stock_disponible >= 0) as stock_positivo,
    COUNT(*) FILTER (WHERE stock_disponible < 0) as stock_negativo,
    COUNT(*) FILTER (WHERE stock_minimo < stock_maximo) as min_menor_max,
    COUNT(*) FILTER (WHERE punto_reorden > stock_minimo) as reorden_mayor_min,
    ROUND(AVG(dias_cobertura)::numeric, 1) as cobertura_promedio_dias
FROM dw.fact_inventario;

\echo ''
\echo '>>> INV-003 CA5: Stock actual por sucursal (ultima fecha)'
SELECT s.nombre,
       COUNT(*) as productos,
       ROUND(AVG(i.dias_cobertura)::numeric, 1) as cobertura_prom,
       COUNT(*) FILTER (WHERE i.stock_disponible <= i.punto_reorden) as en_alerta,
       COUNT(*) FILTER (WHERE i.stock_disponible <= i.stock_minimo) as criticos
FROM dw.fact_inventario i
JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal
JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo
WHERE t.fecha = (SELECT MAX(fecha) FROM dw.dim_tiempo)
GROUP BY s.nombre ORDER BY s.nombre;

-- ============================================================
-- INV-003 CA6: Festivos colombianos (verificado en CA5 arriba)
-- ============================================================

-- ============================================================
-- INV-003 CA8: Pipelines ETL por dominio (verificación indirecta)
-- ============================================================
\echo ''
\echo '>>> INV-003 CA8: Datos cargados por dominio (evidencia de pipelines)'
SELECT 'dim_tiempo' as dominio, COUNT(*) as registros FROM dw.dim_tiempo
UNION ALL SELECT 'dim_producto', COUNT(*) FROM dw.dim_producto
UNION ALL SELECT 'dim_sucursal', COUNT(*) FROM dw.dim_sucursal
UNION ALL SELECT 'dim_proveedor', COUNT(*) FROM dw.dim_proveedor
UNION ALL SELECT 'dim_evento', COUNT(*) FROM dw.dim_evento
UNION ALL SELECT 'fact_ventas', COUNT(*) FROM dw.fact_ventas
UNION ALL SELECT 'fact_inventario', COUNT(*) FROM dw.fact_inventario
UNION ALL SELECT 'app.usuarios', COUNT(*) FROM app.usuarios
ORDER BY dominio;

-- ============================================================
-- INV-003 CA11: ≥ 500,000 registros en fact_ventas
-- ============================================================
\echo ''
\echo '>>> INV-003 CA11: Volumen fact_ventas'
SELECT COUNT(*) as total_fact_ventas,
       CASE WHEN COUNT(*) >= 500000 THEN 'CUMPLE' ELSE 'NO CUMPLE' END as estado
FROM dw.fact_ventas;

-- ============================================================
-- INTEGRIDAD REFERENCIAL (0 huérfanos)
-- ============================================================
\echo ''
\echo '>>> INTEGRIDAD: Huerfanos en fact_ventas'
SELECT
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_producto p ON v.id_producto = p.id_producto WHERE p.id_producto IS NULL) as sin_producto,
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal WHERE s.id_sucursal IS NULL) as sin_sucursal,
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo WHERE t.id_tiempo IS NULL) as sin_tiempo;

\echo ''
\echo '>>> INTEGRIDAD: Huerfanos en fact_inventario'
SELECT
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_producto p ON i.id_producto = p.id_producto WHERE p.id_producto IS NULL) as sin_producto,
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal WHERE s.id_sucursal IS NULL) as sin_sucursal,
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo WHERE t.id_tiempo IS NULL) as sin_tiempo;

-- ============================================================
-- VENTAS POR SUCURSAL (ratio Principal ~5x)
-- ============================================================
\echo ''
\echo '>>> NEGOCIO: Ventas por sucursal'
SELECT s.nombre,
       COUNT(*) as registros,
       ROUND(SUM(v.cantidad)) as unidades,
       ROUND(SUM(v.valor_total)::numeric, 0) as total_cop,
       ROUND(SUM(v.valor_total)::numeric / 1000000, 1) as total_millones
FROM dw.fact_ventas v
JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal
WHERE NOT v.es_devolucion
GROUP BY s.nombre ORDER BY total_cop DESC;

-- ============================================================
-- TOP 10 PRODUCTOS CRÍTICOS
-- ============================================================
\echo ''
\echo '>>> NEGOCIO: Top 10 productos con stock critico (ultima fecha)'
SELECT p.nombre, p.categoria, s.nombre as sucursal,
       i.stock_disponible, i.punto_reorden, i.dias_cobertura
FROM dw.fact_inventario i
JOIN dw.dim_producto p ON i.id_producto = p.id_producto
JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal
JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo
WHERE t.fecha = (SELECT MAX(fecha) FROM dw.dim_tiempo)
  AND i.stock_disponible <= i.stock_minimo
ORDER BY i.dias_cobertura ASC LIMIT 10;

-- ============================================================
-- USUARIOS SEED
-- ============================================================
\echo ''
\echo '>>> APP: Usuarios seed'
SELECT u.email, u.nombre, u.rol, s.nombre as sucursal
FROM app.usuarios u
LEFT JOIN dw.dim_sucursal s ON u.id_sucursal = s.id_sucursal
ORDER BY u.rol, u.nombre;

\echo ''
\echo '============================================================'
\echo 'FIN DEL REPORTE DE VERIFICACION'
\echo '============================================================'
\timing off
