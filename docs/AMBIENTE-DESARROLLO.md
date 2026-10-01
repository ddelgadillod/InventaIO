# Ambiente de desarrollo y pruebas (Windows + Docker)

Cómo levantar desde cero la bodega de datos en Postgres, cargarla con los
datos reales y correr el servicio de predicción (`ml_service`) contra ella.
Comandos para PowerShell; en Linux/macOS son los mismos cambiando las
barras y la forma de pasar variables de entorno.

## 1. Requisitos

- Git y Docker Desktop (con `docker compose`).
- Python 3.11 o superior (para el ETL, que corre fuera de Docker).
- Los insumos del ETL (no se versionan porque son datos del negocio), en la
  carpeta de Drive `InventaIO - DW real (INV-60)/data/raw_real/`.

## 2. Código

```powershell
git clone https://github.com/ddelgadillod/InventaIO.git
cd InventaIO
git checkout develop
```

## 3. Insumos del ETL

Copiar desde Drive a `data\raw_real\` (crear las carpetas):

| Archivo | Destino |
|---|---|
| `ventas_tidy.csv` (viene comprimido: `ventas_tidy_2022_2025.zip`) | `data\raw_real\ventas_tidy.csv` |
| `terminal_sucursal.csv` | `data\raw_real\terminal_sucursal.csv` |
| `inventarioooo.xlsx` | `data\raw_real\inventario\inventarioooo.xlsx` |

Los festivos ya vienen en el repo (`etl_real\festivos_colombia_2022_2027.csv`).
`ventas_tidy.csv` debe tener 2.187.351 filas de datos, del 2022-01-02 al
2025-12-31; su SHA-256 empieza por `c8363ca6b4a4bf2c`
(`Get-FileHash data\raw_real\ventas_tidy.csv`).

## 4. Construir la bodega (ETL)

```powershell
py -3.11 -m venv .venv-etl
.\.venv-etl\Scripts\python -m pip install -r etl_real\requirements.txt
cd etl_real
..\.venv-etl\Scripts\python construir_dim_tiempo.py
..\.venv-etl\Scripts\python construir_dim_sucursal.py
..\.venv-etl\Scripts\python clasificar_productos.py
..\.venv-etl\Scripts\python construir_dim_producto.py --completo
..\.venv-etl\Scripts\python validar_inventario.py
..\.venv-etl\Scripts\python construir_dim_producto.py
..\.venv-etl\Scripts\python simular_proveedores.py
..\.venv-etl\Scripts\python construir_dim_evento.py
..\.venv-etl\Scripts\python construir_fact_ventas.py
..\.venv-etl\Scripts\python construir_fact_inventario_real.py
..\.venv-etl\Scripts\python -m unittest discover -s tests
cd ..
```

Resultado esperado en `data\processed_real\`: `dim_tiempo` 2.190 fechas
(2022-01-02 a 2027-12-31), `dim_producto` 4.449, `fact_ventas` 2.056.210,
`fact_inventario` 11.101. `--completo` en la primera pasada de
`construir_dim_producto.py` es obligatorio (ver `etl_real\README.md`).

## 5. Postgres y carga

```powershell
docker compose up -d postgres
```

La primera vez, el contenedor crea el esquema con `database\init.sql`. Si el
volumen `pgdata` ya existía de una versión anterior, aplicar el esquema a mano
(es idempotente: agrega lo nuevo sin borrar datos). En PowerShell el SQL se
pasa por tubería, porque `<` no funciona:

```powershell
Get-Content database\init.sql | docker compose exec -T postgres psql -U inventaio_user -d inventaio -v ON_ERROR_STOP=1
```

Cargar y verificar (la carga tarda unos 7 minutos; va en una sola
transacción, así que si falla la base queda como estaba):

```powershell
$env:DATABASE_URL = "postgresql://inventaio_user:inventaio_pass_2025@localhost:5432/inventaio"
cd etl_real; ..\.venv-etl\Scripts\python cargar_postgres.py; cd ..
Get-Content database\test-dw-real.SQL | docker compose exec -T postgres psql -U inventaio_user -d inventaio
```

La carga termina con `REPORTE DE CARGA (base vs. CSV)` y todas las tablas en
`OK`. En la verificación no debe aparecer ningún `NO CUMPLE`. Recargar es
seguro: no borra los usuarios de `app.*` ni cambia los `id_*`.

## 6. Servicio de predicción

```powershell
docker compose up -d --build ml-service
Invoke-RestMethod http://localhost:8001/api/health
Invoke-RestMethod http://localhost:8001/api/predict -Method Post -ContentType "application/json" `
  -Body '{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}'
```

`/api/health` debe responder `"bodega": "ok"`. Con los datos 2022-2025, el
ejemplo da rama `intermitente`, `prediccion_q50` 3366,01 y límite superior
4608,72 con `fecha_features` 2025-12-31. Documentación interactiva en
http://localhost:8001/api/docs.

Transferencias entre sucursales (INV-22, ver `docs/INV-22-transferencias.md`):

```powershell
Invoke-RestMethod http://localhost:8001/api/transferencias -Method Post -ContentType "application/json" `
  -Body '{"productos": ["P3937"]}'
```

Con los datos 2022-2025, el arroz P3937 sugiere 572 unidades de la Bodega a
GLORIETA (urgente) y 695 a PRINCIPAL (alta). Sin `productos` se procesa todo
el catálogo de la foto (unos 20 s): 119 traslados. Requiere las columnas
`requiere_frio` y `se_vende_por_kilo` en `dw.dim_producto`: con una bodega
cargada antes de INV-22, aplicar `database\init.sql` y recargar (sección 5).

Compras a proveedor (INV-21, ver `docs/INV-21-compras.md`):

```powershell
Invoke-RestMethod http://localhost:8001/api/compras -Method Post -ContentType "application/json" `
  -Body '{"productos": ["P1632", "00380", "P3937"]}'
```

Con los datos 2022-2025: huevos P1632 compra 4.735 directo a PRINCIPAL (pedido
del martes 6 de enero), el durazno 00380 compra 53 para la Bodega (pedido del 2
de enero) y el arroz P3937 no compra porque la Bodega ya lo tiene. El catálogo
completo tarda unos 20 s: 1.340 líneas. Con una bodega cargada antes de INV-21,
correr `construir_dim_producto.py` y recargar (sección 5) para que los
congelados tengan la marca de frío.

Tests del servicio contra la bodega (opcional, fuera de Docker):

```powershell
cd ml_service
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:POSTGRES_HOST = "localhost"; $env:POSTGRES_PORT = "5432"
.\.venv\Scripts\python -m pytest
cd ..
```

`test_paridad_matriz.py` se salta si no está `data\processed_real\matriz_as_of.parquet`
(se genera con los notebooks 01-07); los demás corren con la bodega cargada.

### Recomendaciones en el Core API (INV-23)

El Core API (puerto 8000) expone las recomendaciones de compras y
transferencias con filtros (ver `docs/INV-23-recomendaciones.md`). Necesita
`ml-service` arriba y los usuarios de prueba en `app.usuarios`; con una base
recién creada la tabla está vacía y nadie puede iniciar sesión.

```powershell
docker compose up -d --build ml-service api
$t = (Invoke-RestMethod http://localhost:8000/api/auth/login -Method Post -ContentType "application/json" `
  -Body '{"email":"gerente@inventaio.co","password":"admin123"}').access_token
Invoke-RestMethod "http://localhost:8000/api/ml/recomendaciones/compras?sucursal=PRINCIPAL&incluir_detalle=false" `
  -Headers @{Authorization = "Bearer $t"}
```

La primera llamada tarda unos 20 s (calcula `ml_service`); las siguientes, con
cualquier filtro, salen de la caché en menos de un segundo. Con los datos
2022-2025, compras de PRINCIPAL da 814 líneas: 164 directas y 650 de la Bodega.

Tests del Core API, dentro del contenedor:

```powershell
docker compose exec api pytest -m "not integracion" --cov=ml
docker compose exec api pytest -m integracion
```

## 7. pgAdmin (opcional)

```powershell
docker compose up -d pgadmin
```

http://localhost:5050 con el usuario y la clave de `docker-compose.yml`.
Registrar el servidor con host `postgres`, puerto `5432`, base `inventaio`,
usuario `inventaio_user`. El diagrama del esquema estrella: clic derecho en
el esquema `dw` → **ERD For Schema**.

## Notas

- Las claves de `docker-compose.yml` son de desarrollo. En un servidor
  compartido, cambiarlas con variables de entorno (`POSTGRES_PASSWORD`, etc.).
- Las ventas de 2026 que llegaron por mes no están en la bodega: el modelo
  trabaja por día y esos reportes no tienen el detalle diario.
