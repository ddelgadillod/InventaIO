-- ============================================================
-- InventAI/o — Script de verificación de bodega de datos REAL (INV-60)
-- Mismo patrón que database/test-dw.SQL (dataset simulado), adaptado a
-- lo que corresponde al dataset real de ventas POS Siigo (2023-2025).
-- Ejecutar después de etl_real/cargar_postgres.py.
-- Uso: psql "$DATABASE_URL" -f database/test-dw-real.SQL
-- ============================================================

\echo '============================================================'
\echo 'INVENTAIO - VERIFICACION DEL DW REAL (INV-60)'
\echo '============================================================'
\pset border 2
\timing on

-- ============================================================
-- Esquema: mismas tablas que el dataset simulado (sin cambio de forma)
-- ============================================================
\echo ''
\echo '>>> Tablas y columnas del esquema estrella'
SELECT table_schema, table_name,
       (SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) as columnas
FROM information_schema.tables t
WHERE table_schema IN ('dw', 'app')
ORDER BY table_schema, table_name;

-- ============================================================
-- INV-60: codigo_item alfanumerico (ya NO es INTEGER)
-- ============================================================
\echo ''
\echo '>>> INV-60: codigo_item admite alfanumerico (esperado: > 0 filas)'
SELECT COUNT(*) as productos_alfanumericos,
       CASE WHEN COUNT(*) > 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar carga' END as estado
FROM dw.dim_producto
WHERE codigo_item ~ '[A-Za-z]';

-- ============================================================
-- INV-60: dim_tiempo en rango real 2023-2025 (no 2013-2017 de Favorita)
-- ============================================================
\echo ''
\echo '>>> INV-60: Rango real de dim_tiempo'
SELECT MIN(fecha) as fecha_inicio, MAX(fecha) as fecha_fin,
       COUNT(*) as total_dias,
       CASE WHEN MIN(fecha) >= '2023-01-01' AND MAX(fecha) <= '2025-12-31'
            THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar que no cargo el dataset simulado' END as estado
FROM dw.dim_tiempo;

\echo ''
\echo '>>> INV-60: dia_semana en convencion ISO (1=lunes, 7=domingo, no 0-6)'
SELECT MIN(dia_semana) as min_dia_semana, MAX(dia_semana) as max_dia_semana,
       CASE WHEN MIN(dia_semana) = 1 AND MAX(dia_semana) = 7
            THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar convencion' END as estado
FROM dw.dim_tiempo;

\echo ''
\echo '>>> INV-60: es_puente_festivo (columna nueva respecto al dataset simulado)'
SELECT COUNT(*) FILTER (WHERE es_puente_festivo) as dias_puente,
       COUNT(*) FILTER (WHERE es_festivo) as dias_festivo
FROM dw.dim_tiempo;

-- ============================================================
-- INV-60: sucursales reales (no las ficticias Principal/Norte/Sur)
-- ============================================================
\echo ''
\echo '>>> INV-60: Sucursales reales'
SELECT codigo_tienda, nombre, tipo, factor_volumen
FROM dw.dim_sucursal ORDER BY codigo_tienda;

\echo ''
\echo '>>> INV-60: Nombres esperados presentes (PRINCIPAL, LA 21, GLORIETA, SIN_SUCURSAL)'
SELECT
  bool_and(nombre IN ('PRINCIPAL', 'LA 21', 'GLORIETA', 'SIN_SUCURSAL')) as todos_los_nombres_son_reales,
  COUNT(*) FILTER (WHERE nombre = 'Sucursal Principal') as sucursales_ficticias_favorita
FROM dw.dim_sucursal;

-- ============================================================
-- INV-60: taxonomia de categoria real (35 categorias, no las 15 genericas)
-- ============================================================
\echo ''
\echo '>>> INV-60: Productos por categoria'
SELECT categoria, COUNT(*) as productos
FROM dw.dim_producto
GROUP BY categoria ORDER BY productos DESC;

\echo ''
\echo '>>> INV-60: Cobertura de categorizacion (esperado: 0 en Abarrotes por defecto sin revisar)'
SELECT COUNT(*) as total_productos, COUNT(DISTINCT categoria) as total_categorias,
       COUNT(*) FILTER (WHERE categoria = 'Abarrotes') as en_abarrotes
FROM dw.dim_producto;

-- ============================================================
-- INV-60: productos excluidos del target de demanda (Anchetas) NO
-- deben aparecer en fact_ventas ni fact_inventario, pero SI en
-- dim_producto (se conservan como referencia de catalogo).
-- ============================================================
\echo ''
\echo '>>> INV-60: Anchetas en dim_producto (referencia, se conservan)'
SELECT COUNT(*) as anchetas_en_catalogo FROM dw.dim_producto WHERE categoria = 'Anchetas';

\echo ''
\echo '>>> INV-60: Anchetas en fact_ventas (esperado: 0 -- se excluyen del target de demanda)'
SELECT COUNT(*) as anchetas_en_fact_ventas,
       CASE WHEN COUNT(*) = 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar exclusion' END as estado
FROM dw.fact_ventas v
JOIN dw.dim_producto p ON v.id_producto = p.id_producto
WHERE p.categoria = 'Anchetas';

\echo ''
\echo '>>> INV-60: Anchetas en fact_inventario (esperado: 0)'
SELECT COUNT(*) as anchetas_en_fact_inventario,
       CASE WHEN COUNT(*) = 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar exclusion' END as estado
FROM dw.fact_inventario i
JOIN dw.dim_producto p ON i.id_producto = p.id_producto
WHERE p.categoria = 'Anchetas';

-- ============================================================
-- Proveedores (100% simulados, sin cambio de forma respecto al original)
-- ============================================================
\echo ''
\echo '>>> Proveedores (simulados)'
SELECT codigo, razon_social, ciudad, lead_time_dias, categorias
FROM dw.dim_proveedor ORDER BY codigo;

-- ============================================================
-- Coherencia de fact_inventario (mismo chequeo que el dataset simulado)
-- ============================================================
\echo ''
\echo '>>> Inventario - coherencia (100% simulado, ver docs/INV-60-compatibilidad-datos.md)'
SELECT
    COUNT(*) as total_registros,
    COUNT(*) FILTER (WHERE stock_disponible >= 0) as stock_positivo,
    COUNT(*) FILTER (WHERE stock_disponible < 0) as stock_negativo,
    COUNT(*) FILTER (WHERE stock_minimo < stock_maximo) as min_menor_max,
    COUNT(*) FILTER (WHERE punto_reorden > stock_minimo) as reorden_mayor_min,
    ROUND(AVG(dias_cobertura)::numeric, 1) as cobertura_promedio_dias
FROM dw.fact_inventario;

-- ============================================================
-- Volumen cargado por dominio
-- ============================================================
\echo ''
\echo '>>> Datos cargados por dominio'
SELECT 'dim_tiempo' as dominio, COUNT(*) as registros FROM dw.dim_tiempo
UNION ALL SELECT 'dim_producto', COUNT(*) FROM dw.dim_producto
UNION ALL SELECT 'dim_sucursal', COUNT(*) FROM dw.dim_sucursal
UNION ALL SELECT 'dim_proveedor', COUNT(*) FROM dw.dim_proveedor
UNION ALL SELECT 'dim_evento', COUNT(*) FROM dw.dim_evento
UNION ALL SELECT 'fact_ventas', COUNT(*) FROM dw.fact_ventas
UNION ALL SELECT 'fact_inventario', COUNT(*) FROM dw.fact_inventario
ORDER BY dominio;

-- ============================================================
-- INTEGRIDAD REFERENCIAL (0 huérfanos esperados)
-- ============================================================
\echo ''
\echo '>>> INTEGRIDAD: Huerfanos en fact_ventas (esperado: 0,0,0)'
SELECT
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_producto p ON v.id_producto = p.id_producto WHERE p.id_producto IS NULL) as sin_producto,
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal WHERE s.id_sucursal IS NULL) as sin_sucursal,
  (SELECT COUNT(*) FROM dw.fact_ventas v LEFT JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo WHERE t.id_tiempo IS NULL) as sin_tiempo;

\echo ''
\echo '>>> INTEGRIDAD: Huerfanos en fact_inventario (esperado: 0,0,0)'
SELECT
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_producto p ON i.id_producto = p.id_producto WHERE p.id_producto IS NULL) as sin_producto,
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal WHERE s.id_sucursal IS NULL) as sin_sucursal,
  (SELECT COUNT(*) FROM dw.fact_inventario i LEFT JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo WHERE t.id_tiempo IS NULL) as sin_tiempo;

-- ============================================================
-- NEGOCIO: ventas por sucursal (factor_volumen real, no el 5x forzado)
-- ============================================================
\echo ''
\echo '>>> NEGOCIO: Ventas por sucursal'
SELECT s.nombre,
       COUNT(*) as registros,
       ROUND(SUM(v.cantidad)) as unidades,
       ROUND(SUM(v.valor_total)::numeric, 0) as total_cop
FROM dw.fact_ventas v
JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal
WHERE NOT v.es_devolucion
GROUP BY s.nombre ORDER BY total_cop DESC;

-- ============================================================
-- NEGOCIO: valor_total incluye IVA (ver nota en init.sql y en
-- docs/INV-60-notas-migracion-dw.md) -- valor_total - valor_total_sin_iva
-- no se puede validar aqui porque el IVA no se carga por separado en
-- fact_ventas; queda documentado como advertencia de interpretacion.
-- ============================================================

\echo ''
\echo '>>> Top 10 productos con stock critico (ultima fecha, excluye Anchetas por construccion)'
SELECT p.nombre, p.categoria, s.nombre as sucursal,
       i.stock_disponible, i.punto_reorden, i.dias_cobertura
FROM dw.fact_inventario i
JOIN dw.dim_producto p ON i.id_producto = p.id_producto
JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal
JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo
WHERE t.fecha = (SELECT MAX(fecha) FROM dw.dim_tiempo)
  AND i.stock_disponible <= i.stock_minimo
ORDER BY i.dias_cobertura ASC LIMIT 10;

\echo ''
\echo '============================================================'
\echo 'FIN DEL REPORTE DE VERIFICACION (DW REAL)'
\echo '============================================================'
