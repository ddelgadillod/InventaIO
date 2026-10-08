# CI/CD de InventAI/o

Qué corre en GitHub Actions, cómo correr lo mismo en local y qué queda fuera
del CI. Requerimientos y decisiones (D1 a D20) en `docs/INV-24-requerimientos.md`.

## Workflows

| Workflow | Cuándo corre | Qué hace |
| --- | --- | --- |
| `ci.yml` (CI) | PR y push a `develop` y `main` | Calidad del código sin datos reales |
| `images.yml` (Imágenes) | PR y push a `develop` y `main`, etiquetas `vX.Y.Z`, lunes a las 6:00 (Bogotá) y a demanda | Imágenes de producción: build, Trivy, verificación, publicación en GHCR |
| Dependabot (`.github/dependabot.yml`) | Lunes a las 6:00 (Bogotá) | PR agrupados hacia `develop` con las actualizaciones de acciones, pip, npm y Docker |

**Jobs de calidad (`ci.yml`)**

| Check | Pasos |
| --- | --- |
| Core API (ruff + pytest) | ruff; pytest sin la marca `integracion`, con cobertura mínima de 70 %; pip-audit; OpenAPI sin diferencias |
| ML Service (ruff + pytest) | ruff; pytest (las de la marca `bodega` se saltan), con cobertura mínima de 90 %; pip-audit; SHA-256 de los modelos |
| ETL (ruff + pytest) | ruff; pytest, con cobertura mínima de 40 %; pip-audit |
| Build frontend (Vite) | ESLint; Vitest con cobertura mínima de 80 %; `npm audit` de producción; build |

**Jobs de imágenes (`images.yml`)**

| Check | Qué hace | Cuándo |
| --- | --- | --- |
| Imagen api, Imagen ml-service e Imagen web | Build; Trivy falla con CRITICAL que tengan corrección y deja los HIGH en el resumen | PR y push |
| Imágenes sanas (docker-compose.verify.yml) | Las tres arrancan sanas, sin root, y Nginx pasa `/api` al Core API | PR y push |
| Publicar … | GHCR con los tags de abajo; es el único job con `packages: write` | Push a `develop` o `main` y etiquetas |
| Escaneo semanal … | Trivy sobre las imágenes publicadas en `develop` | Lunes y a demanda |

Las tres imágenes se publican como `ghcr.io/ddelgadillod/inventaio-{api,ml-service,web}`, con estos tags:
- `sha-<7 caracteres>` siempre;
- `develop` o `main`, según la rama;
- `vX.Y.Z` y `latest` en las etiquetas de versión.

El compose de producción usa `sha-…` o `vX.Y.Z`, nunca `latest`.

Los umbrales de cobertura viven en el `.coveragerc` de cada servicio y en `frontend/vite.config.js`. Así, la corrida local aplica la misma regla que el CI.

## Correr lo mismo en local

Desde la raíz del repositorio, con el entorno conda de `docs/AMBIENTE-DESARROLLO.md`. Ese entorno trae las herramientas de `requirements-dev.txt`.

```bash
# Ruff, con la versión fijada en requirements-dev.txt
~/venvs/inventaio/bin/ruff check api ml_service etl_real

# Pruebas sin Postgres, como en el CI
docker run --rm --network none -v "$PWD/api:/app:ro" -e COVERAGE_FILE=/tmp/.coverage -w /app \
  inventaio-api python -m pytest -p no:cacheprovider -m "not integracion" --cov=.
(cd ml_service && POSTGRES_PORT=1 ~/venvs/inventaio/bin/python -m pytest --cov=.)   # puerto cerrado: sin bodega
(cd etl_real && ~/venvs/inventaio/bin/python -m pytest tests --cov=.)

# Auditoría de dependencias, con las excepciones aceptadas
for s in api ml_service; do
  PATH=~/venvs/inventaio/bin:$PATH python .github/scripts/pip_audit.py -r $s/requirements.txt --no-deps --disable-pip
done
PATH=~/venvs/inventaio/bin:$PATH python .github/scripts/pip_audit.py -r etl_real/requirements.txt

# OpenAPI versionado y hashes de los modelos
docker compose exec api python -m tests.postman.exportar_openapi
git diff --exit-code api/tests/postman/inventaio-core-api.openapi.yml
(cd models && sha256sum -c SHA256SUMS)

# Frontend (Node 22)
cd frontend && npm run lint && npm run test:cov && npm run build && npm audit --omit=dev --audit-level=high; cd ..

# Imágenes de producción: sanas, sin root, y el proxy de Nginx
docker compose -f docker-compose.verify.yml up -d --build --wait --wait-timeout 240
curl -s localhost:18088/api/health
docker compose -f docker-compose.verify.yml down
```

Trivy, con la misma imagen y el mismo digest de `images.yml`:

```bash
TRIVY=aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
mkdir -p /tmp/trivy && docker save inventaio-web:verify -o /tmp/trivy/imagen.tar
docker run --rm -v /tmp/trivy:/scan -v "$PWD/.trivyignore:/trivyignore:ro" "$TRIVY" \
  image --input /scan/imagen.tar --cache-dir /scan/cache --quiet --scanners vuln \
  --ignorefile /trivyignore --severity CRITICAL,HIGH --ignore-unfixed
```

## Pruebas solo locales

La bodega real sale de exportes de Siigo del negocio y no está en GitHub. Por
eso el CI no corre 73 pruebas: 56 de `api` (marca `integracion`) y 17 de
`ml_service` (marca `bodega`). Son las que llevan la cobertura de la API por
encima del 80 %. Se corren en local antes de cada merge a `develop`; la
plantilla de PR tiene la casilla.

```bash
docker compose exec api pytest                                                # 210
(cd ml_service && POSTGRES_HOST=localhost ~/venvs/inventaio/bin/python -m pytest)  # 191 y 1 saltada
npx newman run api/tests/postman/INV-25.postman_collection.json --timeout-request 120000
npx newman run api/tests/postman/INV-26-fix.postman_collection.json
for t in consulta inventario alertas reportes recomendaciones; do bash api/tests/test_$t.sh; done
```

`api/tests/test_auth.sh` cambia contraseñas: no correrlo sobre una base compartida.

## Dependencias

**Dónde se fijan.**
- Producción: el `requirements.txt` de cada servicio. Los de `api` y `ml_service` fijan todas las versiones, transitivas incluidas (pip freeze en un `python:3.11-slim` limpio).
- Desarrollo y CI: `requirements-dev.txt` en la raíz (ruff, pytest, pip-audit). Es el único lugar donde se fija ruff. Subirlo es un cambio deliberado: la 0.16 activa reglas nuevas por defecto, entre ellas B008, que choca con los `Depends()` de FastAPI.

**Actualizar una dependencia de producción**
1. Cambiar su versión en el `requirements.txt` del servicio.
2. Volver a congelar en limpio y reemplazar las líneas fijadas, dejando el encabezado:
   ```bash
   docker run --rm -v "$PWD/api:/x:ro" python:3.11-slim \
     sh -c 'pip install -q -r /x/requirements.txt && pip check && pip freeze --exclude pip'
   ```
3. Correr pip-audit.
4. Reconstruir los contenedores: `docker compose up -d --build --no-deps ml-service api`.
5. Actualizar el entorno conda:
   ```bash
   ~/venvs/inventaio/bin/pip install -r ml_service/requirements.txt -r requirements-dev.txt
   ```
6. Correr las pruebas solo locales.

Los PR de Dependabot se aceptan igual.

**Excepciones.** Una vulnerabilidad conocida que no tiene corrección, o que no
aplica, se acepta por escrito y con fecha de vencimiento. Al vencer, el CI
vuelve a fallar hasta que alguien la revise.
- pip-audit: `.github/pip-audit-excepciones.txt`, una línea por excepción (ID, vencimiento, paquete y motivo). Hoy tiene ecdsa y python-jose, que vencen el 2 de noviembre de 2026, antes del despliegue.
- Trivy: `.trivyignore`, con el motivo en un comentario y `exp:AAAA-MM-DD`. Hoy no tiene ninguna.

## Imágenes

| Imagen | Base | Usuario | Puerto | Notas |
| --- | --- | --- | --- | --- |
| `api` | `python:3.11-slim` | 10001 | 8000 | El target `prod` es el de por defecto. El `dev`, que usa el compose de desarrollo, agrega `requirements-dev.txt` |
| `ml-service` | `python:3.11-slim` | 10001 | 8001 | Los modelos van dentro. Llegan por el contexto adicional `models`, y el build falla si no coinciden con `models/SHA256SUMS` |
| `web` | `nginxinc/nginx-unprivileged:1.30-alpine` | 101 | 8080 | Sin root no se puede abrir el 80; el host publica 80 y 443 hacia 8080 y 8443 |

Las de producción:
- no llevan pruebas, pip, setuptools ni wheel;
- aplican los parches de Debian al construir;
- tienen `HEALTHCHECK`.

La raíz del repositorio nunca es contexto de build: en el disco de desarrollo tiene `data/` (exportes del negocio) y `.env`.

**Modelos.** `notebooks/exportar_parametros_features.py` regenera `models/SHA256SUMS` al final de cada exportación. La exportación de los modelos (`exportar_modelos_nivel1_v2.py`) llama a ese script. El CI falla si:
- un archivo de `models/` cambia sin volver a exportar;
- hay un archivo de `models/` que no está en `SHA256SUMS`.

**OpenAPI.** Si cambia la API, se regenera con `docker compose exec api python -m tests.postman.exportar_openapi` y el YAML va en el mismo commit.

## Cadena de suministro

- **Acciones:** van fijadas por SHA completo, con la versión en un comentario; Dependabot las actualiza.
- **Permisos:** `contents: read` en todo el workflow; `packages: write` solo en el job que publica. `actions/checkout` no deja las credenciales en el disco.
- **Trivy:**
  - corre por su imagen oficial fijada por digest, no por `trivy-action`, cuyas etiquetas se reescribieron en marzo de 2026 con código que robaba secretos (CVE-2026-33634);
  - escanea la imagen exportada a un tar, sin el socket de Docker y sin secretos.

## Configuración del repositorio (persona propietaria)

Esto no vive en el código: se hace una vez en GitHub, al integrar INV-24.

1. **Ruleset de `main` (D17).** En Settings → Rules → Rulesets → New branch ruleset:
   - Nombre `main`, en estado Active, con destino la rama por defecto (`main`).
   - Activar Restrict deletions, Block force pushes y Require a pull request before merging (0 aprobaciones: hay una sola persona).
   - Activar Require status checks to pass, con estos checks:
     - Core API (ruff + pytest)
     - ML Service (ruff + pytest)
     - ETL (ruff + pytest)
     - Build frontend (Vite)
     - Imagen api
     - Imagen ml-service
     - Imagen web
     - Imágenes sanas (docker-compose.verify.yml)
   - Sin lista de bypass.

   `develop` queda sin ruleset: se sigue integrando con merge local y push, y el CI avisa después del push.
2. **Escaneo de secretos.** En Settings → Advanced Security (antes, "Code security"), activar Secret scanning y Push protection. Son gratis en repositorios públicos.
3. **Paquetes.** Después de la primera publicación, en cada paquete de GHCR (perfil → Packages):
   - confirmar que esté conectado al repositorio;
   - fijar su visibilidad. Pública, como el repositorio, deja que la instancia de INV-34 los descargue sin credenciales; las imágenes no traen datos del negocio.

## Agregar un servicio

Por ejemplo, el agente de PLN (`nlp-agent`):

1. **Dockerfile:** sin root, con `HEALTHCHECK` y sin herramientas de prueba en la imagen final.
2. **`images.yml`:** una fila en la lista `servicios`.
3. **`docker-compose.verify.yml`:** el servicio, y su comprobación en el job `verificar`.
4. **Si es Python:**
   - un job en `ci.yml` como el de ML Service;
   - un `requirements.txt` congelado y un `.coveragerc` con su umbral;
   - su carpeta en `src` de `ruff.toml`;
   - en Dependabot, su carpeta en `pip` y `docker`.
5. **Ollama:** no se construye; se usa la imagen oficial con tag fijo.

## Contrato con INV-34

| Elemento | Definición |
| --- | --- |
| Imágenes | Las de GHCR, con tag `sha-…` o `vX.Y.Z` |
| Salud | `GET /api/health` en `api` y `ml-service`, y `GET /` en `web`; las tres con `HEALTHCHECK` |
| Usuario y puertos | Ninguna corre como root. `web` escucha en 8080 (8443 con TLS) |
| Red | Solo `web` publica puertos. `api`, `ml-service`, Redis, Ollama y el agente quedan en la red interna; Postgres es RDS |
| Modelos | Dentro de la imagen de `ml-service`; S3 queda solo para las copias de seguridad |
| Variables | `POSTGRES_*`, `REDIS_*`, `ML_SERVICE_URL`, `JWT_SECRET_KEY`, `MODELOS_DIR`, sin valores por defecto utilizables en producción (historia de hardening) |
| Despliegue | Un rol de IAM por OIDC, sin claves guardadas en GitHub; SSM en la instancia; entorno `production` con aprobación manual; pruebas de humo contra los endpoints de salud y reversa al tag anterior |
| OIDC | El repositorio es anterior al 15 de julio de 2026 y conserva el claim `sub` clásico (`repo:ddelgadillod/InventaIO:…`), salvo que se active el formato nuevo o se renombre |
