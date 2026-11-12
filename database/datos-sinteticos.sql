-- ============================================================
-- InventAI/o — Datos sintéticos para probar la migración de la base (INV-34)
-- Llenan las ocho tablas de dw con valores inventados y deterministas (sin random()),
-- para que el job base-de-datos del CI pruebe volcar, restaurar y validar sin la bodega
-- real, que no está en GitHub. No se parecen al negocio y no sirven para los modelos.
-- Solo corre sobre una base recién creada con init.sql: se niega si dw ya tiene datos.
-- Uso: scripts/bd/probar.sh (lo aplica sobre una base temporal).
-- ============================================================

\set ON_ERROR_STOP 1

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM dw.dim_tiempo) OR EXISTS (SELECT 1 FROM dw.fact_ventas) THEN
        RAISE EXCEPTION 'datos-sinteticos.sql es solo para una base vacía: dw ya tiene filas';
    END IF;
END $$;

BEGIN;

-- Calendario de dos años
INSERT INTO dw.dim_tiempo (fecha, anio, mes, dia, dia_semana, nombre_dia, semana_iso, trimestre,
                           es_fin_semana, es_quincena, temporada)
SELECT d::date,
       extract(year FROM d)::smallint,
       extract(month FROM d)::smallint,
       extract(day FROM d)::smallint,
       extract(isodow FROM d)::smallint,
       (ARRAY['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'])[extract(isodow FROM d)::int],
       extract(week FROM d)::smallint,
       extract(quarter FROM d)::smallint,
       extract(isodow FROM d) >= 6,
       extract(day FROM d) = 15 OR d::date = (date_trunc('month', d) + interval '1 month - 1 day')::date,
       CASE WHEN extract(month FROM d) = 12 THEN 'navidad' ELSE 'normal' END
FROM generate_series(date '2024-01-01', date '2025-12-31', interval '1 day') AS d;

INSERT INTO dw.dim_sucursal (codigo_tienda, nombre, ciudad, departamento, tipo)
VALUES (1, 'SUCURSAL SINTETICA A', 'Ciudad A', 'Depto A', 'principal'),
       (2, 'SUCURSAL SINTETICA B', 'Ciudad B', 'Depto B', 'estandar'),
       (3, 'SUCURSAL SINTETICA C', 'Ciudad C', 'Depto C', 'estandar');

INSERT INTO dw.dim_producto (codigo_item, nombre, familia, categoria, es_perecedero,
                             precio_base, costo_base, margen_pct, requiere_frio, se_vende_por_kilo)
SELECT format('SINT-%s', lpad(i::text, 4, '0')),
       format('Producto sintético %s', i),
       format('FAMILIA %s', 1 + i % 4),
       format('CATEGORIA %s', 1 + i % 5),
       i % 6 = 0,
       1000 + i * 250,
       700 + i * 180,
       round((1 - (700 + i * 180)::numeric / (1000 + i * 250)) * 100, 2),
       i % 9 = 0,
       i % 11 = 0
FROM generate_series(1, 40) AS i;

INSERT INTO dw.dim_proveedor (codigo, razon_social, nit, ciudad, lead_time_dias, categorias)
SELECT format('PROV-%s', i), format('Proveedor sintético %s', i), format('90000000%s', i),
       'Ciudad A', 2 + i, ARRAY[format('CATEGORIA %s', i)]
FROM generate_series(1, 5) AS i;

INSERT INTO dw.dim_evento (fecha, tipo, nombre, descripcion)
SELECT date '2024-01-01' + i * 70, 'festivo', format('Evento sintético %s', i), NULL
FROM generate_series(1, 10) AS i;

INSERT INTO dw.producto_proveedor (id_producto, id_proveedor)
SELECT p.id_producto, 1 + p.id_producto % 5
FROM dw.dim_producto p;

-- 20.000 ventas repartidas por producto, sucursal y día; una de cada 101 es devolución
INSERT INTO dw.fact_ventas (id_producto, id_sucursal, id_tiempo, id_proveedor, cantidad,
                            valor_unitario, valor_total, costo_unitario, costo_total,
                            en_promocion, es_devolucion)
SELECT 1 + (i * 7919) % 40,
       1 + i % 3,
       1 + (i * 104729) % 731,
       1 + i % 5,
       CASE WHEN i % 101 = 0 THEN -1 ELSE 1 + i % 5 END,
       1000 + (i % 50) * 100,
       (CASE WHEN i % 101 = 0 THEN -1 ELSE 1 + i % 5 END) * (1000 + (i % 50) * 100),
       700 + (i % 50) * 70,
       (CASE WHEN i % 101 = 0 THEN -1 ELSE 1 + i % 5 END) * (700 + (i % 50) * 70),
       i % 17 = 0,
       i % 101 = 0
FROM generate_series(1, 20000) AS i;

-- Inventario de fin de mes por producto y sucursal
INSERT INTO dw.fact_inventario (id_producto, id_sucursal, id_tiempo, stock_disponible,
                                stock_minimo, stock_maximo, punto_reorden, dias_cobertura)
SELECT p.id_producto, s.id_sucursal, t.id_tiempo,
       10 + (p.id_producto * s.id_sucursal + t.mes) % 90,
       10, 120, 25,
       round(((10 + (p.id_producto * s.id_sucursal + t.mes) % 90) / 3.0)::numeric, 1)
FROM dw.dim_producto p
CROSS JOIN dw.dim_sucursal s
JOIN dw.dim_tiempo t ON t.fecha = (date_trunc('month', t.fecha) + interval '1 month - 1 day')::date;

COMMIT;
