-- ============================================================
-- InventAI/o — Script de verificación de bodega de datos REAL (INV-60)
-- Mismo patrón que database/test-dw.SQL (dataset simulado), adaptado a
-- lo que corresponde al dataset real de ventas POS Siigo (desde 2022).
-- INV-20: calendario extendido hasta 2027, atributos de producto,
-- producto_proveedor y la vista dw.v_ventas_diarias_netas.
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
-- dim_tiempo: desde la primera venta real (2022, no 2013-2017 de
-- Favorita) y, desde INV-20, mas alla de la ultima venta (horizonte de
-- prediccion; hasta config.FECHA_FIN_CALENDARIO).
-- ============================================================
\echo ''
\echo '>>> Rango de dim_tiempo vs. rango de ventas'
SELECT MIN(t.fecha) as fecha_inicio, MAX(t.fecha) as fecha_fin, COUNT(*) as total_dias,
       (SELECT MAX(t2.fecha) FROM dw.fact_ventas v JOIN dw.dim_tiempo t2 ON v.id_tiempo = t2.id_tiempo) as ultima_venta,
       CASE WHEN MIN(t.fecha) >= '2022-01-01'
             AND MAX(t.fecha) >= (SELECT MAX(t2.fecha) + 60 FROM dw.fact_ventas v JOIN dw.dim_tiempo t2 ON v.id_tiempo = t2.id_tiempo)
            THEN 'CUMPLE' ELSE 'NO CUMPLE -- el calendario no cubre el horizonte despues de la ultima venta' END as estado
FROM dw.dim_tiempo t;

\echo ''
\echo '>>> INV-20: dias sin cobertura de festivos (esperado: 0 anios sin ningun festivo)'
SELECT COUNT(*) as anios_sin_festivos,
       CASE WHEN COUNT(*) = 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- extender etl_real/festivos_colombia_*.csv' END as estado
FROM (SELECT anio FROM dw.dim_tiempo GROUP BY anio HAVING NOT bool_or(es_festivo)) s;

\echo ''
\echo '>>> INV-20: cierres programados (1 de enero y Viernes Santo de cada anio)'
SELECT anio, string_agg(fecha::text || ' ' || nombre_festivo, ', ' ORDER BY fecha) as cierres
FROM dw.dim_tiempo WHERE es_cierre_programado GROUP BY anio ORDER BY anio;

\echo ''
\echo '>>> INV-20: cierres programados con ventas (esperado: 0)'
SELECT COUNT(*) as ventas_en_dias_de_cierre,
       CASE WHEN COUNT(*) = 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- revisar la regla de cierre' END as estado
FROM dw.fact_ventas v JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
WHERE t.es_cierre_programado;

\echo ''
\echo '>>> INV-20: marcas de calendario comercial por anio'
SELECT anio,
       COUNT(*) FILTER (WHERE es_semana_santa) as dias_semana_santa,
       COUNT(*) FILTER (WHERE es_periodo_prima) as dias_prima,
       COUNT(*) FILTER (WHERE bloque_diciembre = 'novena') as novena,
       COUNT(*) FILTER (WHERE bloque_diciembre = 'nochebuena_navidad') as nochebuena_navidad,
       COUNT(*) FILTER (WHERE bloque_diciembre = 'fin_de_anio') as fin_de_anio,
       COUNT(*) FILTER (WHERE bloque_diciembre = 'enero_postnavidad') as enero_postnavidad
FROM dw.dim_tiempo GROUP BY anio ORDER BY anio;

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
\echo '>>> Nombres esperados (PRINCIPAL, LA 21, GLORIETA, SIN_SUCURSAL y BODEGA_CENTRAL desde INV-61)'
SELECT
  bool_and(nombre IN ('PRINCIPAL', 'LA 21', 'GLORIETA', 'SIN_SUCURSAL', 'BODEGA_CENTRAL')) as todos_los_nombres_son_reales,
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
\echo '>>> INV-20: atributos de priorizacion (condiciones 1-5; esperado 111 / 93 / 429 / 2 / 204 con los datos 2022-2025)'
SELECT COUNT(*) FILTER (WHERE requiere_espacio_bodega) as espacio_bodega,
       COUNT(*) FILTER (WHERE es_perecedero_estricto) as perecedero_estricto,
       COUNT(*) FILTER (WHERE es_refrigerado) as refrigerado,
       COUNT(*) FILTER (WHERE es_papel_higienico_grande) as papel_higienico_grande,
       COUNT(*) FILTER (WHERE es_temporada) as temporada,
       COUNT(*) FILTER (WHERE volumen_cm3 IS NOT NULL OR peso_g IS NOT NULL) as con_tamano
FROM dw.dim_producto;

\echo ''
\echo '>>> INV-22/INV-21: marcas de logistica (esperado 329 con frio, 124 refrigerados sin frio, 24 con frio sin ser refrigerados -- los Congelados menos el override P431 -- y 64 por kilo con los datos 2022-2025)'
SELECT COUNT(*) FILTER (WHERE requiere_frio) as requiere_frio,
       COUNT(*) FILTER (WHERE es_refrigerado AND NOT requiere_frio) as refrigerado_sin_frio,
       COUNT(*) FILTER (WHERE requiere_frio AND NOT es_refrigerado) as frio_sin_refrigerado,
       COUNT(*) FILTER (WHERE se_vende_por_kilo) as se_vende_por_kilo
FROM dw.dim_producto;

\echo ''
\echo '>>> INV-22/INV-21: productos con frio que tienen stock en la Bodega Central (la Bodega no tiene frio: pueden salir, no entrar; esperado 1 producto y 2 unidades -- la papa precocida congelada 02276; los 35 refrigerados por categoria que hay alli son enlatados, leche en polvo, caldos y salsas)'
SELECT COUNT(DISTINCT p.id_producto) as productos, COALESCE(SUM(fi.stock_disponible), 0) as unidades
FROM dw.fact_inventario fi
JOIN dw.dim_producto p ON p.id_producto = fi.id_producto
JOIN dw.dim_sucursal s ON s.id_sucursal = fi.id_sucursal
WHERE s.tipo = 'bodega_central' AND p.requiere_frio AND fi.stock_disponible > 0;

SELECT p.codigo_item, p.nombre, p.categoria, fi.stock_disponible
FROM dw.fact_inventario fi
JOIN dw.dim_producto p ON p.id_producto = fi.id_producto
JOIN dw.dim_sucursal s ON s.id_sucursal = fi.id_sucursal
WHERE s.tipo = 'bodega_central' AND p.requiere_frio AND fi.stock_disponible > 0
ORDER BY fi.stock_disponible DESC, p.codigo_item;

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

-- INV-20: informativo. La exclusion de Anchetas aplica al target de
-- demanda (fact_ventas), no al inventario: con el inventario real (INV-61)
-- aparecen accesorios y canastos para armar anchetas que si son stock
-- fisico (decision del negocio, 2026-09-29: se conservan). El "esperado: 0"
-- venia del inventario simulado.
\echo ''
\echo '>>> Anchetas en fact_inventario (informativo: stock fisico de accesorios y canastos, se conserva)'
SELECT COUNT(*) as filas, COUNT(DISTINCT i.id_producto) as productos,
       SUM(i.stock_disponible) as unidades
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

\echo ''
\echo '>>> INV-20: producto_proveedor (esperado: un proveedor por producto del catalogo)'
SELECT (SELECT COUNT(*) FROM dw.producto_proveedor) as filas,
       (SELECT COUNT(*) FROM dw.dim_producto) as productos,
       (SELECT COUNT(*) FROM dw.dim_producto p WHERE NOT EXISTS
            (SELECT 1 FROM dw.producto_proveedor pp WHERE pp.id_producto = p.id_producto)) as productos_sin_proveedor;

\echo ''
\echo '>>> INV-20: proveedor de fact_ventas coincide con producto_proveedor (esperado: 0 discrepancias)'
SELECT COUNT(*) as discrepancias,
       CASE WHEN COUNT(*) = 0 THEN 'CUMPLE' ELSE 'NO CUMPLE -- fact_ventas generado con otra asignacion de proveedores' END as estado
FROM dw.fact_ventas v
LEFT JOIN dw.producto_proveedor pp ON pp.id_producto = v.id_producto AND pp.id_proveedor = v.id_proveedor
WHERE pp.id_producto IS NULL;

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
UNION ALL SELECT 'producto_proveedor', COUNT(*) FROM dw.producto_proveedor
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

-- ============================================================
-- INV-20: vista dw.v_ventas_diarias_netas (la que consume el servicio
-- de prediccion) cuadra con fact_ventas
-- ============================================================
\echo ''
\echo '>>> INV-20: vista de ventas diarias netas vs. fact_ventas (esperado: diferencia 0)'
SELECT (SELECT ROUND(SUM(unidades), 3) FROM dw.v_ventas_diarias_netas) as unidades_vista,
       (SELECT ROUND(SUM(cantidad), 3) FROM dw.fact_ventas WHERE NOT es_devolucion AND cantidad > 0) as unidades_hechos,
       (SELECT COUNT(*) FROM dw.v_ventas_diarias_netas WHERE tipo_sucursal IN ('principal', 'estandar')) as filas_sucursales_fisicas;

-- La ultima fecha se toma de fact_inventario (no de dim_tiempo, que desde
-- INV-20 llega mas alla del ultimo dato).
\echo ''
\echo '>>> Top 10 productos con stock critico (ultima fecha de inventario)'
SELECT p.nombre, p.categoria, s.nombre as sucursal,
       i.stock_disponible, i.punto_reorden, i.dias_cobertura
FROM dw.fact_inventario i
JOIN dw.dim_producto p ON i.id_producto = p.id_producto
JOIN dw.dim_sucursal s ON i.id_sucursal = s.id_sucursal
JOIN dw.dim_tiempo t ON i.id_tiempo = t.id_tiempo
WHERE t.fecha = (SELECT MAX(t2.fecha) FROM dw.fact_inventario i2 JOIN dw.dim_tiempo t2 ON i2.id_tiempo = t2.id_tiempo)
  AND i.stock_disponible <= i.stock_minimo
ORDER BY i.dias_cobertura ASC LIMIT 10;

\echo ''
\echo '============================================================'
\echo 'FIN DEL REPORTE DE VERIFICACION (DW REAL)'
\echo '============================================================'
