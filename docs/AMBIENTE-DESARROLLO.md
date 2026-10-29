# Ambiente de desarrollo y pruebas (Linux: Ubuntu en WSL2 + Docker)

Cómo levantar desde cero la bodega de datos en Postgres, cargarla con los
datos reales y correr los servicios (`ml_service`, Core API y frontend)
contra ella. El ambiente es Linux, como el servidor de producción y el CI
(`ubuntu-latest`): en Windows se usa Ubuntu en WSL2, con el repositorio dentro
del disco de Linux (`~/InventaIO`), no en `C:\`. Todos los comandos son de bash.

## 1. Requisitos

- **Ubuntu en WSL2** (o un Linux nativo). El repositorio va en el disco de
  Linux: en `/mnt/c/...` los montajes de Docker son lentos, Vite no detecta los
  cambios y los binarios nativos del frontend no son los de Linux.
- **Docker Desktop con la integración de WSL** activada para la distro
  (Settings → Resources → WSL integration). No instalar además `docker.io` con
  `apt`: dos motores en el mismo socket se pisan. Si ya está, apagarlo con
  `sudo systemctl disable --now docker.service docker.socket containerd.service`.
  `docker info --format '{{.OperatingSystem}}'` debe decir "Docker Desktop" y
  `docker compose version` debe responder.
- **Python 3.11** para el ETL y las pruebas de `ml_service`, que corren fuera de
  Docker. El Python de Ubuntu 24.04 es 3.12 y no trae `venv`; lo más simple es
  un entorno de conda (Miniforge), sin `sudo`.
- **Node 22.12 o superior** para el frontend, con nvm (sin `sudo`). El Node 18
  de `apt` no sirve.
- `git`, `curl`, `jq` y `rsync` (vienen con Ubuntu).
- Los insumos del ETL (no se versionan porque son datos del negocio), en la
  carpeta de Drive `InventaIO - DW real (INV-60)/data/raw_real/`.

```bash
# Python 3.11 (Miniforge ya instalado)
conda create -y -p ~/venvs/inventaio python=3.11
~/venvs/inventaio/bin/pip install -r etl_real/requirements.txt -r ml_service/requirements.txt \
  -r requirements-dev.txt   # pytest, ruff y pip-audit, con las versiones del CI

# Node 22
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 22
```

## 2. Código

```bash
git clone https://github.com/ddelgadillod/InventaIO.git ~/InventaIO
cd ~/InventaIO
git checkout develop
cp .env.example .env   # o copiar el .env del equipo; .env no se versiona
```

En Linux, git deja todo en LF; `.gitattributes` lo exige además para los `.sh`.
La carpeta se llama `InventaIO` a propósito: Docker Compose toma de ahí el nombre
del proyecto (`inventaio`) y con él el del volumen de la bodega
(`inventaio_pgdata`).

## 3. Insumos del ETL

Copiar desde Drive a `data/raw_real/` (crear las carpetas):

| Archivo | Destino |
|---|---|
| `ventas_tidy.csv` (viene comprimido: `ventas_tidy_2022_2025.zip`) | `data/raw_real/ventas_tidy.csv` |
| `terminal_sucursal.csv` | `data/raw_real/terminal_sucursal.csv` |
| `inventarioooo.xlsx` | `data/raw_real/inventario/inventarioooo.xlsx` |

Los festivos ya vienen en el repo (`etl_real/festivos_colombia_2022_2027.csv`).
`ventas_tidy.csv` debe tener 2.187.351 filas de datos, del 2022-01-02 al
2025-12-31; su SHA-256 empieza por `c8363ca6b4a4bf2c`
(`sha256sum data/raw_real/ventas_tidy.csv`).

Para traer archivos desde Windows, copiarlos dentro de WSL
(`rsync -rt /mnt/c/.../data/ ~/InventaIO/data/`), no trabajar sobre `/mnt/c`.
Un archivo de varios GB puede fallar con rsync por el sistema de archivos
compartido (`Cannot allocate memory`); `dd if=... of=... bs=64M` sí lo copia.
Para verificarlo, comparar el SHA-256 de cada lado (en Windows,
`Get-FileHash`), que es más rápido que releerlo con `cmp` a través de `/mnt/c`.

## 4. Construir la bodega (ETL)

```bash
PY=~/venvs/inventaio/bin/python
cd etl_real
$PY construir_dim_tiempo.py
$PY construir_dim_sucursal.py
$PY clasificar_productos.py
$PY construir_dim_producto.py --completo
$PY validar_inventario.py
$PY construir_dim_producto.py
$PY simular_proveedores.py
$PY construir_dim_evento.py
$PY construir_fact_ventas.py
$PY construir_fact_inventario_real.py
$PY -m unittest discover -s tests
cd ..
```

Resultado esperado en `data/processed_real/`: `dim_tiempo` 2.190 fechas
(2022-01-02 a 2027-12-31), `dim_producto` 4.449, `fact_ventas` 2.056.210,
`fact_inventario` 11.101. `--completo` en la primera pasada de
`construir_dim_producto.py` es obligatorio (ver `etl_real/README.md`).

## 5. Postgres y carga

```bash
docker compose up -d postgres
```

La primera vez, el contenedor crea el esquema con `database/init.sql`. Si el
volumen `pgdata` ya existía de una versión anterior, aplicar el esquema a mano
(es idempotente: agrega lo nuevo sin borrar datos):

```bash
docker compose exec -T postgres psql -U inventaio_user -d inventaio -v ON_ERROR_STOP=1 < database/init.sql
```

Cargar y verificar (la carga tarda unos 7 minutos; va en una sola
transacción, así que si falla la base queda como estaba):

```bash
export DATABASE_URL="postgresql://inventaio_user:inventaio_pass_2025@localhost:5432/inventaio"
(cd etl_real && ~/venvs/inventaio/bin/python cargar_postgres.py)
docker compose exec -T postgres psql -U inventaio_user -d inventaio < database/test-dw-real.SQL
```

La carga termina con `REPORTE DE CARGA (base vs. CSV)` y todas las tablas en
`OK`. En la verificación no debe aparecer ningún `NO CUMPLE`. Recargar es
seguro: no borra los usuarios de `app.*` ni cambia los `id_*`.

## 6. Servicio de predicción

```bash
docker compose up -d --build ml-service
curl -s localhost:8001/api/health | jq
curl -s localhost:8001/api/predict -H "Content-Type: application/json" \
  -d '{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}' | jq
```

El build de las imágenes (`ml-service` y `api`) retoma las descargas de pip que
se cortan (`--resume-retries`) y las guarda en una caché de BuildKit: con la
red lenta tarda más, pero no se cae por un timeout. Si aun así falla, volver a
correrlo; lo ya descargado no se vuelve a bajar.

`/api/health` debe responder `"bodega": "ok"`. Con los datos 2022-2025, el
ejemplo da rama `intermitente`, `prediccion_q50` 3366,01 y límite superior
4608,72 con `fecha_features` 2025-12-31. Documentación interactiva en
http://localhost:8001/api/docs.

Transferencias entre sucursales (INV-22, ver `docs/INV-22-transferencias.md`):

```bash
curl -s localhost:8001/api/transferencias -H "Content-Type: application/json" \
  -d '{"productos": ["P3937"]}' | jq
```

Con los datos 2022-2025, el arroz P3937 sugiere 572 unidades de la Bodega a
GLORIETA (urgente) y 695 a PRINCIPAL (alta). Sin `productos` se procesa todo
el catálogo de la foto (unos 20 s): 119 traslados. Requiere las columnas
`requiere_frio` y `se_vende_por_kilo` en `dw.dim_producto`: con una bodega
cargada antes de INV-22, aplicar `database/init.sql` y recargar (sección 5).

Compras a proveedor (INV-21, ver `docs/INV-21-compras.md`):

```bash
curl -s localhost:8001/api/compras -H "Content-Type: application/json" \
  -d '{"productos": ["P1632", "00380", "P3937"]}' | jq
```

Con los datos 2022-2025: huevos P1632 compra 4.735 directo a PRINCIPAL (pedido
del martes 6 de enero), el durazno 00380 compra 53 para la Bodega (pedido del 2
de enero) y el arroz P3937 no compra porque la Bodega ya lo tiene. El catálogo
completo tarda unos 20 s: 1.340 líneas. Con una bodega cargada antes de INV-21,
correr `construir_dim_producto.py` y recargar (sección 5) para que los
congelados tengan la marca de frío.

Tests del servicio contra la bodega (fuera de Docker):

```bash
cd ml_service
POSTGRES_HOST=localhost POSTGRES_PORT=5432 ~/venvs/inventaio/bin/python -m pytest
cd ..
```

`test_paridad_matriz.py` se salta si no está `data/processed_real/matriz_as_of.parquet`
(se genera con los notebooks 01-07); los demás corren con la bodega cargada.

### Recomendaciones en el Core API (INV-23)

El Core API (puerto 8000) expone las recomendaciones de compras y
transferencias con filtros (ver `docs/INV-23-recomendaciones.md`). Necesita
`ml-service` arriba y los usuarios de prueba en `app.usuarios`; con una base
recién creada la tabla está vacía y nadie puede iniciar sesión. El seed los
crea, o los restablece con la clave `admin123` (por ejemplo, después de probar
el cambio de contraseña): `gerente@`, `admin.principal@`, `admin.norte@`,
`admin.sur@` y `bodega@inventaio.co`.

```bash
docker compose up -d --build ml-service api
docker exec inventaio-api python -m scripts.seed_usuarios
T=$(curl -s localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq -r .access_token)
curl -s "localhost:8000/api/ml/recomendaciones/compras?sucursal=PRINCIPAL&incluir_detalle=false" \
  -H "Authorization: Bearer $T" | jq '.resumen'
```

La primera llamada tarda unos 20 s (calcula `ml_service`); las siguientes, con
cualquier filtro, salen de la caché en menos de un segundo. Con los datos
2022-2025, compras de PRINCIPAL da 814 líneas: 164 directas y 650 de la Bodega.

Tests del Core API, dentro del contenedor (el código está montado desde
`~/InventaIO/api`, así que corren sobre lo que hay en el disco):

```bash
docker compose exec api pytest -m "not integracion" --cov=ml
docker compose exec api pytest -m integracion
```

### Core API contra la bodega real (INV-25 y fix de INV-26)

Los endpoints de Release 1 (consulta, inventario, alertas y reportes) quedaron
homologados con la bodega real (ver `docs/INV-25-homologacion.md`) y ajustados
en el fix de INV-26 (`docs/INV-26-fix.md`). Con los usuarios de prueba cargados:

```bash
docker compose exec api pytest --cov=consulta --cov=inventario --cov=alertas --cov=reportes \
  --cov=core.ubicaciones --cov=core.productos --cov=core.semaforo --cov=ml --cov=scripts
```

Y los scripts con `curl` y `jq`: `bash api/tests/test_consulta.sh` (y
`test_inventario.sh`, `test_alertas.sh`, `test_reportes.sh`,
`test_recomendaciones.sh`). `test_auth.sh` cambia contraseñas: no correrlo
sobre una base compartida.

El pronóstico también está en el Core API, con token:
`POST http://localhost:8000/api/ml/predict`, con el mismo cuerpo que el de
`ml_service`.

Para Postman, `api/tests/postman/` trae las colecciones con los casos de INV-25
(`INV-25.postman_collection.json`) y del fix de INV-26
(`INV-26-fix.postman_collection.json`), que se corren con el Runner o con
`npx newman run <colección>`, y el OpenAPI del Core API en YAML para explorar
los endpoints. Pasos en `docs/INV-25-pruebas.md` y `docs/INV-26-fix.md`. Si
cambia la API, el YAML se regenera con
`docker exec inventaio-api python -m tests.postman.exportar_openapi`.

### Frontend (fix de INV-26)

Requiere Node 22.12 o superior (`frontend/.nvmrc`), como el CI. Con el Core API
arriba y los usuarios del seed, desde `~/InventaIO/frontend`:

```bash
nvm use            # toma la versión de .nvmrc
npm ci             # instala lo del lockfile, con los binarios de Linux
npm run dev        # http://localhost:5173, con proxy a la API
npm run test:cov   # pruebas con cobertura (mínimo 80 %)
npm run build
npm audit          # 0 vulnerabilidades
```

Chrome en Windows abre http://localhost:5173 servido desde WSL sin
configuración extra (WSL reenvía los puertos de Linux a Windows); al revés no:
desde Ubuntu, `localhost` no llega a un servidor que corra en Windows.

La app tiene Dashboard, Inventario, Alertas, Reportes, Predicciones (INV-26) y
Recomendaciones (INV-27), con los tres roles. La guía para recorrerlas a mano,
con los valores esperados, está en `docs/INV-26-pruebas-pantallas.md`.

Para probar el frontend compilado detrás de Nginx, como en producción, se usa el
servicio `web` del compose, que solo arranca con su perfil:

```bash
docker compose --profile web up -d --build --no-deps web   # http://localhost:8080
bash scripts/probar_nginx_timeout.sh              # los tiempos de espera del proxy
```

La configuración y los tiempos de espera están en `frontend/README.md`.

El histórico de ventas de la vista de predicciones está en
`GET /api/consulta/productos/{id_producto}/ventas?sucursal_id=1`: con los datos
2022-2025, P1632 en PRINCIPAL vende 4.608 unidades en la última ventana de 15
días hábiles (17 al 31 de diciembre). Ver `docs/INV-26-fix.md`.

## 7. pgAdmin (opcional)

```bash
docker compose up -d pgadmin
```

http://localhost:5050 con el usuario y la clave de `docker-compose.yml`.
Registrar el servidor con host `postgres`, puerto `5432`, base `inventaio`,
usuario `inventaio_user`. El diagrama del esquema estrella: clic derecho en
el esquema `dw` → **ERD For Schema**.

## 8. Pasar de una copia en Windows a WSL

Así se migró el ambiente el 2026-10-05 (fix de INV-26), por si hay que
repetirlo en otra máquina:

1. Hacer commit de lo pendiente en la copia de Windows (o anotarlo para
   copiarlo) y clonarla en WSL: `git clone /mnt/c/.../InventaIO ~/InventaIO`.
   Luego `git remote rename origin windows` y
   `git remote add origin https://github.com/ddelgadillod/InventaIO.git`.
2. Copiar lo que no está en git: `.env` (con `chmod 600`), `data/`, los
   documentos ignorados y `.git/info/exclude`. Los archivos copiados desde
   `/mnt/c` llegan con permisos 777 y, si venían de Windows, con CRLF: pasarlos
   a LF (`dos2unix`), sobre todo `.gitignore`, porque git en Linux no aplica las
   reglas que terminan en `\r`.
3. `docker compose up -d` desde `~/InventaIO`: el proyecto se sigue llamando
   `inventaio`, así que reutiliza el volumen de la bodega y las imágenes. Los
   contenedores pasan a montar el código desde Linux.
4. En `frontend/`, `npm ci` (no copiar `node_modules`, que trae los binarios de
   Windows).
5. Dejar de usar la copia de Windows: dos copias con `docker compose` comparten
   los nombres de los contenedores.

## Notas

- Las claves de `docker-compose.yml` son de desarrollo. En un servidor
  compartido, cambiarlas con variables de entorno (`POSTGRES_PASSWORD`, etc.).
  El compose actual es de desarrollo (código montado, `--reload`, pgAdmin): el
  despliegue en un servidor necesita su propia configuración.
- Si el sudo de Ubuntu pide una clave olvidada, desde PowerShell
  `wsl -d Ubuntu -u root passwd <usuario>` pone una nueva.
- Las ventas de 2026 que llegaron por mes no están en la bodega: el modelo
  trabaja por día y esos reportes no tienen el detalle diario.
