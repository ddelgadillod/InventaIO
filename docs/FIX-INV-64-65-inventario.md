# Fix INV-64 e INV-65 · Lista de inventario: semáforo inválido y orden por venta reciente

| Campo | Valor |
| --- | --- |
| Jira | INV-64 (error) e INV-65 (error), enlazados |
| Endpoint | `GET /api/consulta/inventario` (`api/inventario/router.py`) |
| Rama | `fix/INV-64-65-inventario`, desde `develop` (`4942662`) |
| Lo encontró | INV-32: el sondeo del Core API (C12) y la revisión del usuario de los críticos de GLORIETA (I10) |

## 1. Qué pasaba

**INV-64.** `?semaforo=xx` respondía 200 con las 11.101 filas sin filtrar. La causa: el filtro se aplicaba solo si el valor existía (`if semaforo in SEMAFORO_CONDICION`) y el parámetro era texto libre. Quien se equivocaba en el filtro recibía datos que parecían filtrados y no lo estaban.

**INV-65.** La lista se ordenaba solo por `dias_cobertura ASC`. Todo producto con stock 0 tiene cobertura 0, así que los 111 críticos con stock 0 de GLORIETA empataban, y el orden entre ellos quedaba a criterio de PostgreSQL. La primera página mezclaba productos que ya no se venden con agotados que sí se venden, y la paginación no era estable.

Cifras de GLORIETA, semáforo crítico, al 31-dic-2025:

| Grupo | Productos |
| --- | --- |
| Críticos | 173 |
| Con stock 0 | 111 |
| Sin ventas en 30 días | 105 (61 %) |
| Sin ventas en 90 días | 69 (40 %) |
| Con ventas en 30 días | 68 |

De los 10 primeros que salían antes, 6 sí vendieron en 30 días y 4 no.

## 2. Qué se cambió

| # | Cambio | Decisión |
| --- | --- | --- |
| F1 | `semaforo` es un enum (`ok`, `bajo`, `critico`, `inconsistencia`): un valor desconocido da **422** con los válidos, y el OpenAPI lo declara | INV-64 |
| F2 | Orden: `(ventas_30d > 0) DESC, dias_cobertura ASC, ventas_30d DESC, nombre, id_sucursal`. Primero lo que se vende; los agotados sin ventas, al final; el nombre y la sucursal desempatan, así que la paginación es estable | Usuario, 19-oct («con venta reciente primero») |
| F3 | Cada fila trae **`ventas_30d`**: las unidades vendidas en los 30 días que terminan en la fecha de la foto, sin devoluciones, como en reportes | Usuario, 19-oct |
| F4 | En la **Bodega Central**, `ventas_30d` son las ventas de las 3 sucursales. La Bodega no vende directo, y es el mismo proxy de demanda que usa el ETL para su cobertura (`etl_real/construir_fact_inventario_real.py`) | Criterio del ETL. Sin él, todas las filas de la Bodega quedarían al final |
| F5 | El agente (`consultar_inventario`) muestra la columna «Ventas 30 d» y, si hay filas de la Bodega, le aclara al modelo que esas ventas son de la red | Alcance de INV-65 |

**Sin cambios:**
- **El semáforo.** Un producto con stock 0 y sin ventas en 90 días (69 en GLORIETA) sigue siendo «crítico». Cambiarlo mueve el KPI de productos en riesgo, el Dashboard y las alertas de reglas (K3 y K9 de INV-26), y se decide aparte. Para esos productos ya existe la alerta `sin_movimiento`.
- **El frontend.** La pantalla de Inventario muestra el orden tal como llega, así que mejora sin tocarla. Su selector de estado usa los 4 valores del enum, y `buildQS` no envía el filtro vacío («Todos los estados»), como verifica `client.test.js`.

## 3. Verificación (19-oct, bodega real)

- **Primera página de GLORIETA crítico.** Antes: VELON N. 2 (0 ventas), TOALLA KOTEX (4), CALADITOS (2)… Ahora: BIANCHI MINI BOMBON * 30 (13), MASMELO MILLOWS (12), JUGO HIT PET *1.5ML (11)…
- **La Bodega.** SAL REFISAL *1000GR tiene stock 0 en la Bodega y 1.176 unidades vendidas en 30 días en la red. Es una señal que antes quedaba escondida.
- **Costo.** La consulta tarda de 0,37 a 0,52 s, contra 0,29–0,39 s antes: unos 100 ms por agregar 30 días de `dw.fact_ventas` (2,06 millones de filas).
- **Pruebas del Core API:** 253, con las 67 de integración. Las nuevas:
  - `tests/test_inventario_orden.py`, sin base y en el CI: el 422, el orden y la consulta;
  - `tests/test_inventario_orden_integracion.py`: 173 sin repetidos en 2 páginas, los 68 con ventas primero, el orden dentro del grupo, la página estable y las ventas de la red en la Bodega.
- **Cobertura del Core API:** 77 % (el umbral es 70 %).
- **Agente:** 235 pruebas. La de contrato ahora compara el enum del semáforo con el OpenAPI.
- **OpenAPI versionado** regenerado: enum de `semaforo`, `ventas_30d` y la descripción del orden.

## 4. Cómo probarlo

```bash
cd ~/InventaIO
TOK=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# INV-64: 422 con los valores válidos
curl -s "localhost:8000/api/consulta/inventario?semaforo=xx" -H "Authorization: Bearer $TOK"

# INV-65: la primera página de GLORIETA crítico, con ventas_30d
curl -s "localhost:8000/api/consulta/inventario?sucursal_id=3&semaforo=critico&page_size=10" -H "Authorization: Bearer $TOK" \
  | python3 -c 'import sys,json;[print(i["nombre_producto"], i["stock_disponible"], i["ventas_30d"]) for i in json.load(sys.stdin)["items"]]'

# Pruebas (dentro del contenedor, con la bodega)
docker exec inventaio-api python -m pytest -q tests/test_inventario_orden.py tests/test_inventario_orden_integracion.py
```

- **En la app:** Inventario → Estado «Crítico» → sucursal GLORIETA. Los primeros son los agotados que se venden.
- **En el chat:** con el agente corriendo (guía de `docs/INV-32-herramientas-agente.md` §4), `scripts/preguntar_agente.py --rol gerente "¿Qué productos están críticos en GLORIETA?"` muestra la columna «Ventas 30 d».
