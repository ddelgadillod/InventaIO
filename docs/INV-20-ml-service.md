# INV-20 — ML Service: Dockerfile + endpoint de predicción

Microservicio HTTP independiente (`ml_service/`) que expone los 3
modelos campeones de Nivel 1 (pronóstico de demanda a 15 días hábiles,
INV-17) vía `POST /api/predict`. Sigue el mismo patrón de código que
`api/` (FastAPI, `core/config.py` con `pydantic-settings`, routers con
`APIRouter`, schemas Pydantic, `/api/health`, `docs_url="/api/docs"`),
pero es un servicio Docker propio, no un router más de `api/`.

## Decisiones de diseño (se apartan del texto literal de algunos
criterios de la HU, a pedido explícito del usuario — documentado para
que quede claro qué se decidió y por qué)

### 1. Carga de modelo: local, NO desde MLflow en runtime

El criterio 4 de la HU pide "carga modelo desde MLflow". Se implementó
distinto: el servicio carga `models/nivel1_<rama>.joblib` **directamente
del repo** al arrancar (`core/modelo_loader.py`), sin descargar nada del
servidor MLflow (`http://172.16.0.147:5000`) en runtime.

**Por qué**: el `.joblib` ya está versionado en `models/` desde INV-17
— agregar una descarga en vivo desde MLflow en cada arranque introduce
una dependencia de red dura e innecesaria (si el servidor MLflow está
caído o inaccesible, el servicio no arrancaría, para servir un archivo
que ya está disponible localmente). MLflow sigue siendo la fuente de
trazabilidad del entrenamiento — `models/nivel1_metadata.json` (de
INV-17) trae `fecha_generacion` y las métricas de referencia de la
validación walk-forward, y el endpoint expone `modelo_entrenado_en` con
ese dato en cada respuesta.

### 2. Fuente de features: extracto local, no Postgres en vivo

`producto_id`/`sucursal_id` son el **código de negocio** (`codigo_item`,
ej. `"P841"`) y el **nombre de sucursal** (ej. `"PRINCIPAL"`) — las
mismas claves que usa todo el pipeline de modelado (INV-14/15/17), no
el `SERIAL` de Postgres que usa `api/`. El servicio lee
`ml_service/data/features_snapshot.parquet`, un extracto de
`matriz_as_of.parquet` (INV-15) con la fila más reciente por par,
generado por `scripts/generar_datos_locales.py`.

**Por qué**: nunca se confirmó que `etl_real/cargar_postgres.py` se
haya corrido con el dato real en este repo — construir el endpoint
sobre esa base sería una dependencia no verificada. Reimplementar en
SQL la lógica as-of de `07_matriz_as_of.ipynb` para consultar Postgres
en vivo sería mucho más trabajo y una fuente de bugs nueva, para un
beneficio (features "en vivo") que tampoco es real hoy — el inventario
de origen (INV-61) ya es una foto a una sola fecha, no una serie.
Reconciliar `producto_id`/`sucursal_id` con los `SERIAL` de Postgres
queda para la HU que integre el frontend con predicciones.

### 3. `horizonte`: validado, no generalizado

Los 3 modelos solo se entrenaron para demanda acumulada a **15 días
hábiles fijos** (`HORIZONTE` en `07_matriz_as_of.ipynb`/
`08_nivel1_demanda.ipynb`). El endpoint acepta el parámetro `horizonte`
(cumple el contrato de la HU) pero devuelve `422` si no es `15` — no
hay forma honesta de generalizar a otro horizonte sin reentrenar
(escalar linealmente no está justificado estadísticamente, la demanda
no escala así con el horizonte).

### 4. `interpretacion`: traducción en lenguaje directo, por reglas

A pedido del usuario, tras revisar manualmente los 3 casos (uno por
rama): el endpoint agrega un campo `interpretacion` con una frase corta
y accionable, generada por `prediccion/interpretacion.py` — reglas
fijas sobre los números ya calculados (rama, `alpha_negocio`), sin
modelo de lenguaje, determinístico y testeado (`tests/test_interpretacion.py`).
En español neutro, directo. Ejemplos reales de esta corrida:

- `suave_no_perecedero` (cuantil alto, `alpha=0.893`): *"Demanda
  estable. Proyección: 75 unidades en 15 días hábiles. Cobertura
  recomendada: hasta 99 unidades."*
- `suave_perecedero` (cuantil bajo, `alpha=0.167` — el caso especial):
  *"Demanda estable, producto perecedero. Proyección: 15 unidades en 15
  días hábiles. El límite superior no incluye margen de seguridad: el
  modelo evita sobre-stock para reducir merma. No usar como cota de
  reposición."*
- `intermitente`: *"Demanda intermitente. Proyección: 2 unidades en 15
  días hábiles. Cobertura recomendada: hasta 4 unidades."*

No reemplaza al futuro agente NLP (Llama 3.1/RAG) del roadmap de
InventaIO — es una traducción mínima y confiable, no lenguaje generado.

### 5. Intervalo de confianza: `[0, pred_q_negocio]`, no un intervalo simétrico

El modelo produce `pred_q50` (mediana, comparable contra el piso por
WAPE) y `pred_q_negocio` (cuantil de negocio asimétrico, `alpha=0.893`
no perecedero / `0.167` perecedero, con recalibración conformal donde
aplica — INV-17). No hay un segundo cuantil bajo entrenado, así que el
intervalo se devuelve como `[0, pred_q_negocio]` — para perecederos
esto es explícitamente un cuantil **bajo** (`alpha=0.167`, el negocio
asume `Co=1.0`/merma total, ver `docs/INV-17-modelo-baseline.md` §2),
documentado en la respuesta (`alpha_negocio`), no ocultado.

### 6. Docker no disponible en este servidor

`docker: command not found` en el servidor donde se desarrolló esta HU.
El `Dockerfile` y la entrada en `docker-compose.yml` se entregan como
artefactos correctos (cumplen los criterios que piden su existencia),
pero **no se pudieron construir/correr ni verificar acá**. La
verificación funcional real se hizo corriendo el servicio directo con
`uvicorn` dentro de un entorno Python aislado (`ml_service/.venv/`,
gitignorado — mismo patrón que `api/.venv/`). Si se necesita verificar
en Docker Compose, hay que hacerlo en una máquina que sí tenga Docker
instalado.

## Datos de prueba: diversos, con contraste contra un histórico real

`scripts/generar_datos_locales.py` genera DOS extractos distintos de
`matriz_as_of.parquet`:

1. `ml_service/data/features_snapshot.parquet` — la fila más reciente
   por `(codigo_item, sucursal)`, lo que consume el endpoint en
   producción.
2. `ml_service/tests/fixtures/casos_prueba.parquet` — una muestra
   **diversa** (varias ramas, varios folds/orígenes de
   `matriz_as_of.parquet`) que **conserva `target_demanda_15d`** (el
   valor real que ocurrió). `tests/test_contraste_historico.py` corre
   el modelo sobre esas filas y compara la predicción contra ese
   histórico real — cotas de sanidad (predicción no negativa, orden de
   magnitud razonable frente al WAPE ya documentado en INV-17), no una
   aserción de exactitud.

Ambos son regenerables (no versionados en git, mismo patrón que
`data/processed_real/`).

## Estructura

```
ml_service/
├── main.py                      # FastAPI app, lifespan carga modelos+snapshot
├── requirements.txt
├── Dockerfile
├── pytest.ini / .coveragerc
├── core/
│   ├── config.py                 # Settings: MODELOS_DIR, FEATURES_SNAPSHOT_PATH, HORIZONTE_SOPORTADO
│   └── modelo_loader.py          # carga los 3 .joblib locales
├── prediccion/
│   ├── motor.py                  # blending puro (mismo cálculo que exportar_modelos_nivel1.py)
│   ├── features.py                # FeatureStore + determinar_rama
│   ├── interpretacion.py          # traducción en lenguaje directo, por reglas fijas
│   └── router.py                  # POST /api/predict
├── schemas/prediccion.py         # Pydantic request/response
├── scripts/generar_datos_locales.py
└── tests/
    ├── conftest.py, test_motor.py, test_features.py, test_interpretacion.py,
    └── test_contraste_historico.py, test_router.py
```

## Contrato del endpoint

`POST /api/predict`
```json
// request
{"producto_id": "P841", "sucursal_id": "PRINCIPAL", "horizonte": 15}
```
- `200`: ver `schemas/prediccion.py::PrediccionResponse`.
- `422`: `horizonte != 15`.
- `404`: `(producto_id, sucursal_id)` sin historia suficiente en el
  snapshot (mismo criterio de cold-start que `07`, no se inventa una
  predicción).

`GET /api/health` → `{"status": "ok", "service": "inventaio-ml-service", "modelos_cargados": [...]}`.
OpenAPI en `/api/docs` / `/api/openapi.json`.

## Cómo correr (sin Docker)

```bash
cd ml_service
python3 -m venv --system-site-packages .venv   # reusa pandas/lightgbm/scikit-learn del env etl
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python3 scripts/generar_datos_locales.py
./.venv/bin/python3 -m pytest tests/ --cov=. --cov-report=term-missing
./.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
```

## Verificación de esta corrida

- **Datos locales**: `scripts/generar_datos_locales.py` generó
  `features_snapshot.parquet` (producción) y `casos_prueba.parquet` con
  45 filas, 15 por rama (`intermitente`/`suave_no_perecedero`/`suave_perecedero`).
- **Endpoint en vivo, ejemplo por rama** (sin Docker, `uvicorn` directo
  dentro del `.venv`) — antes de agregar `interpretacion`, la respuesta
  ya traía los demás campos correctos:
  - `suave_no_perecedero` (P1235/GLORIETA): `prediccion_q50=75.33`,
    `intervalo_confianza={limite_superior: 98.6, alpha_negocio: 0.893}`.
  - `suave_perecedero` (P1811/GLORIETA): `prediccion_q50=14.99`,
    `intervalo_confianza={limite_superior: 14.96, alpha_negocio: 0.167}`
    — el límite superior queda por DEBAJO de la mediana a propósito
    (cuantil bajo, ver sección 5).
  - `intermitente` (P513/GLORIETA): `prediccion_q50=1.97`,
    `intervalo_confianza={limite_superior: 4.42, alpha_negocio: 0.893}`.
  - `horizonte=30` → `422` con el mensaje de la limitación (confirma el
    criterio 2 de la HU).
- **Tests + cobertura** (con `interpretacion.py` incluido): `pytest --cov`
  — **26 tests, todos pasan, 98% de cobertura** (160 statements, 3 sin
  cubrir: manejo de errores de `core/modelo_loader.py` y una rama de
  `interpretacion.py` no ejercitados porque los modelos reales siempre
  están presentes y los casos de prueba no cubren el `else` de
  `rama` desconocida). Muy por encima del 80% pedido en el DoD.

## Pendiente / fuera de alcance de esta HU

1. Reconciliar `producto_id`/`sucursal_id` con los `SERIAL` de Postgres.
2. Cargar el dato real en Postgres (`cargar_postgres.py`).
3. Integración con el frontend/agente NLP que consuma este endpoint.
4. Refrescar `features_snapshot.parquet` automáticamente — hoy es un
   paso manual.
5. Construir/correr el contenedor Docker realmente — bloqueado por la
   ausencia de Docker en este servidor; los artefactos (`Dockerfile`,
   entrada en `docker-compose.yml`) están listos para probarse en una
   máquina que sí tenga Docker.
