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
