-- InventAI/o — Huella de la base para validar una migración (INV-34; sección 5 de
-- docs/INV-34-requerimientos.md).
-- Solo lee: no crea ni cambia nada, así que corre igual en el origen, en staging y en RDS.
-- Escribe una fila por comprobación, «nombre|valor». El valor es el md5 del resultado, o el
-- resultado mismo con -v detalle=1. H8 da «al dia» o «ATRASADA», que no es un dato del negocio.
-- H10 (el informe de test-dw-real.SQL) lo agrega scripts/bd/comun.sh.
-- Las tablas y secuencias de dw salen del catálogo: una tabla nueva entra sola.
-- Se usa a través de scripts/bd/volcar.sh y scripts/bd/validar.sh.

\set ON_ERROR_STOP 1

-- H1. Columnas de dw y app: tipo, nulabilidad y valor por defecto (ordenadas por nombre,
-- para que no importe el orden en que se agregaron)
SELECT 'H1 columnas', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT string_agg(format('%s.%s.%s %s %s %s', n.nspname, c.relname, a.attname,
                             format_type(a.atttypid, a.atttypmod),
                             CASE WHEN a.attnotnull THEN 'not null' ELSE 'null' END,
                             coalesce(pg_get_expr(d.adbin, d.adrelid), '')),
                      E'\n' ORDER BY n.nspname, c.relname, a.attname) AS t
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE n.nspname IN ('dw', 'app') AND c.relkind IN ('r', 'v')
      AND a.attnum > 0 AND NOT a.attisdropped
) s;

-- H2. Restricciones: claves primarias, foráneas, únicas y checks
SELECT 'H2 restricciones', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT string_agg(format('%s.%s %s %s %s', n.nspname, c.relname, k.conname, k.contype,
                             pg_get_constraintdef(k.oid)),
                      E'\n' ORDER BY n.nspname, c.relname, k.conname) AS t
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('dw', 'app')
) s;

-- H3. Índices
SELECT 'H3 indices', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT string_agg(format('%s.%s %s', schemaname, indexname, indexdef),
                      E'\n' ORDER BY schemaname, indexname) AS t
    FROM pg_indexes
    WHERE schemaname IN ('dw', 'app')
) s;

-- H4. Vistas
SELECT 'H4 vistas', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT coalesce(string_agg(format('%s %s', viewname, definition), E'\n' ORDER BY viewname), '') AS t
    FROM pg_views
    WHERE schemaname = 'dw'
) s;

-- H5. Filas de cada tabla de dw
SELECT format($q$SELECT %L, CASE WHEN %L = '1' THEN t ELSE md5(t) END
                FROM (SELECT count(*)::text AS t FROM %I.%I) s$q$,
              'H5 filas dw.' || c.relname, :'detalle', n.nspname, c.relname)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'dw' AND c.relkind = 'r'
ORDER BY c.relname
\gexec

-- H6. Suma de los hashes de las filas de cada tabla de dw: no depende del orden de las
-- filas ni del de las columnas (to_jsonb ordena las claves). sum(bigint) da numeric,
-- así que no se desborda
SELECT format($q$SELECT %L, CASE WHEN %L = '1' THEN t ELSE md5(t) END
                FROM (SELECT coalesce(sum(('x' || left(md5(to_jsonb(x)::text), 15))::bit(60)::bigint), 0)::text AS t
                      FROM %I.%I x) s$q$,
              'H6 hash de filas dw.' || c.relname, :'detalle', n.nspname, c.relname)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'dw' AND c.relkind = 'r'
ORDER BY c.relname
\gexec

-- H7. Ventas por año, mes y sucursal: dice dónde está una diferencia que H5 o H6 encontraron
SELECT 'H7 ventas por mes y sucursal', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT coalesce(string_agg(format('%s-%s sucursal %s: %s filas, cantidad %s, valor %s',
                                      anio, mes, id_sucursal, filas, cantidad, valor),
                               E'\n' ORDER BY anio, mes, id_sucursal), '') AS t
    FROM (
        SELECT t.anio, t.mes, v.id_sucursal, count(*) AS filas,
               sum(v.cantidad) AS cantidad, sum(v.valor_total) AS valor
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON t.id_tiempo = v.id_tiempo
        GROUP BY t.anio, t.mes, v.id_sucursal
    ) g
) s;

-- H8. Cada secuencia de dw va por delante de su columna: si quedara atrás, la próxima
-- inserción chocaría con una clave existente
SELECT format($q$SELECT %L, CASE WHEN (SELECT last_value FROM %s) >= coalesce((SELECT max(%I) FROM %I.%I), 0)
                             THEN 'al dia' ELSE 'ATRASADA' END$q$,
              'H8 secuencia ' || s.relname, s.oid::regclass, a.attname, n.nspname, t.relname)
FROM pg_class s
JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass AND d.deptype = 'a'
JOIN pg_class t ON t.oid = d.refobjid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE s.relkind = 'S' AND n.nspname = 'dw'
ORDER BY s.relname
\gexec

-- H9. La vista que lee el ml-service
SELECT 'H9 vista de ventas diarias', CASE WHEN :'detalle' = '1' THEN t ELSE md5(t) END
FROM (
    SELECT format('%s filas, unidades %s, valor %s', count(*), sum(unidades), sum(valor)) AS t
    FROM dw.v_ventas_diarias_netas
) s;
