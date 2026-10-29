# INV-20 — ML Service: Dockerfile + endpoint de predicción

Microservicio HTTP independiente (`ml_service/`) que expone los 3
modelos campeones de Nivel 1 (pronóstico de demanda a 15 días hábiles,
INV-17) vía `POST /api/predict`. Sigue el mismo patrón de código que
`api/` (FastAPI, `core/config.py` con `pydantic-settings`, routers con
`APIRouter`, schemas Pydantic, `/api/health`, `docs_url="/api/docs"`),
pero es un servicio Docker propio, no un router más de `api/`.

> **Fix INV-20 (bodega en Postgres).** El servicio ya **no** lee un extracto
> de la matriz de entrenamiento: calcula las features de cada predicción
> leyendo la bodega de datos en Postgres (esquema `dw`), la misma base que
> usa `api/`. La matriz (`matriz_as_of.parquet`) queda solo para entrenar y
> validar. Detalle en la sección 2 y en "Verificación del fix".

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

### 2. Fuente de datos: la bodega en Postgres (fix INV-20)

La primera versión leía `ml_service/data/features_snapshot.parquet`, un
extracto de `matriz_as_of.parquet` armado a mano, porque nunca se había
cargado la bodega real en Postgres. Eso tenía tres problemas: las features
quedaban congeladas en el último origen de evaluación (2025-12-12, no el
último dato), el extracto no se regeneró cuando cambió la matriz (quedó con
5.857 pares y sin los datos de 2022) y no estaba versionado. Con la bodega ya
cargada y validada en Postgres (commit `fix(dw)` de este mismo fix), el
servicio calcula las features en cada petición:

| Qué | De dónde |
|---|---|
| Venta diaria neta del par | `dw.v_ventas_diarias_netas` (sin devoluciones, cantidad > 0, como el panel de `01`) |
| Días hábiles históricos | días con al menos una venta neta en el negocio (como `fechas_habiles` de `01`) |
| Días hábiles futuros y marcas de calendario | `dw.dim_tiempo` (hasta 2027; `es_cierre_programado` = 1 de enero y Viernes Santo) |
| Condiciones 1-5 del producto | columnas de `dw.dim_producto` (`etl_real/atributos_producto.py`) |
| Parámetros del cálculo | `models/nivel1_parametros_features.json` (congelados con los modelos) |

`prediccion/features.py` reproduce las fórmulas de
`notebooks/07_matriz_as_of.ipynb` (rejilla de días hábiles con ceros en
`float32`, trail de 15 días, nivel medio de 60, días desde la última venta,
frecuencia/ADI/CV²/racha as-of y factor de calendario de los próximos 15 días
hábiles). `models/nivel1_parametros_features.json` lo escribe
`notebooks/exportar_parametros_features.py` a partir de los mismos artefactos
que usó la matriz (verifica sus huellas); el exportador v2 lo regenera en cada
reentrenamiento. **Son parámetros del entrenamiento, no se recalculan en
producción**: los coeficientes de calendario se estimaron con la historia de
entrenamiento.

En producción las features estáticas (frecuencia, ADI, CV², racha) se miden
con toda la historia hasta el día de la predicción. En la matriz de
entrenamiento se medían hasta el `train_end` de cada fold, para no filtrar
información del periodo de prueba. `frecuencia_as_of` cuenta días con venta
desde 2022, así que crece con el tiempo: en un reentrenamiento conviene
revisarla (p. ej. como proporción).

`producto_id`/`sucursal_id` son el **código de negocio** (`codigo_item`,
ej. `"P841"`) y el **nombre de sucursal** (ej. `"PRINCIPAL"`), las claves de
todo el pipeline de modelado. Desde el fix, también se aceptan
`id_producto`/`id_sucursal` (el `SERIAL` de Postgres que usa `api/`), y la
respuesta trae las cuatro.

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
En español neutro, directo. Ejemplos:

- `suave_no_perecedero` (cuantil alto, `alpha=0.893`): *"Demanda
  estable. Proyección: 75 unidades en 15 días hábiles. Cobertura
  recomendada: hasta 99 unidades."*
- `suave_perecedero` (cuantil bajo, `alpha=0.167` — el caso especial):
  *"Demanda estable, producto perecedero. Proyección: 15 unidades en 15
  días hábiles. El límite superior no incluye margen de seguridad: el
  modelo evita sobre-stock para reducir merma. No usar como cota de
  reposición."*
- `intermitente`: *"Demanda intermitente. Proyección: 3.366 unidades en 15
  días hábiles. Cobertura recomendada: hasta 4.609 unidades."*

Desde el fix de INV-26 (A12), las cantidades van en la unidad de venta y con el
formato de la app: punto de miles, "1 unidad" en singular y, en los productos
por kilo, kg con un decimal ("Proyección: 0,01 kg…"). Una cantidad distinta de
0 nunca se escribe 0.

No reemplaza al futuro agente NLP (Llama 3.1/RAG) del roadmap de
InventaIO — es una traducción mínima y confiable, no lenguaje generado.

### 5. Intervalo de confianza: `[0, pred_q_negocio]`, no un intervalo simétrico

El modelo produce `pred_q50` (mediana, comparable contra el piso por
WAPE) y `pred_q_negocio` (cuantil de negocio asimétrico, `alpha=0.893`
no perecedero / `0.167` perecedero, con los costos `Cu`/`Co` validados por
el negocio). No hay un segundo cuantil bajo entrenado, así que el
intervalo se devuelve como `[0, pred_q_negocio]` — para perecederos
esto es explícitamente un cuantil **bajo** (`alpha=0.167`, `Co=1.0`/merma
total, ver `docs/INV-17-modelo-baseline.md` §2), documentado en la
respuesta (`alpha_negocio`), no ocultado.

Tipos de paquete que soporta `motor.predecir`: `lightgbm`/`ensamble` (v1) y,
desde el exportador v2, `relativo` (rama `intermitente`: LightGBM cuantílico
sobre `y/base`, con `base = nivel_medio_60d·15 + 1`, predicción = `base·q`,
recalibración conformal por estrato de volumen `base·(q + offset)`) y
`baseline_cuantil` (ramas suaves: q50 = media móvil y cuantil de negocio =
razón empírica por estrato × `(media_movil + 1)`). Política, cifras y
limitaciones: `docs/FIX-EDA-MODELADO-NIVEL1.md`.

### 6. Docker no disponible en el servidor de desarrollo

El servidor donde se desarrolló no tiene Docker. El servicio se verificó
con `uvicorn` en un entorno aislado (`ml_service/.venv/`) contra un Postgres
16 levantado con la **misma imagen del `docker-compose.yml`**
(`postgres:16-alpine`) mediante Apptainer. El `docker-compose.yml` como
archivo se valida en una máquina con Docker (ver
`docs/AMBIENTE-DESARROLLO.md`). En el fix se corrigió que el contenedor
buscaba los modelos en `/models` mientras el compose los monta en
`/app/models` (ahora `MODELOS_DIR` va en el `environment`), y que no tenía
la conexión a Postgres.

## Pruebas

Todas con `ml_service/.venv/bin/python -m pytest` (desde `ml_service/`):

| Archivo | Qué prueba | Necesita |
|---|---|---|
| `test_motor.py`, `test_interpretacion.py` | predicción pura por tipo de paquete e interpretación | nada |
| `test_features.py` | las features contra una réplica del cálculo de `07` sobre series sintéticas, proyección de días hábiles (salta los cierres), cold start | nada |
| `test_router.py` | el endpoint con una bodega en memoria: códigos e ids, `fecha_corte`, 404/422/503 | modelos |
| `test_bodega_integracion.py` | el endpoint contra Postgres y la predicción frente a la **demanda real** de los 15 días hábiles siguientes a una `fecha_corte` pasada | bodega cargada |
| `test_paridad_matriz.py` | features y predicciones calculadas desde la bodega **idénticas** a las de `matriz_as_of.parquet` (la matriz de entrenamiento, verificada por huella) | bodega + matriz |

Los marcados `bodega` se saltan con un mensaje claro si no hay conexión o la
bodega está vacía (p. ej. en un clon sin cargar). Ya no hay datos de prueba
en parquet dentro de `ml_service/`.

## Estructura

```
ml_service/
├── main.py                      # FastAPI app; lifespan carga modelos + parámetros y crea la conexión a la bodega
├── requirements.txt
├── Dockerfile
├── pytest.ini / .coveragerc
├── core/
│   ├── config.py                 # MODELOS_DIR, POSTGRES_*, CACHE_CALENDARIO_SEGUNDOS, HORIZONTE_SOPORTADO
│   ├── database.py               # engine SQLAlchemy (solo lectura)
│   └── modelo_loader.py          # 3 .joblib + nivel1_parametros_features.json (verifica que las features coincidan)
├── prediccion/
│   ├── bodega.py                 # consultas a dw.* (BodegaPostgres)
│   ├── features.py               # cálculo de features (funciones puras, fórmulas de 07) + determinar_rama
│   ├── motor.py                  # predicción pura: lightgbm / ensamble (v1) y relativo / baseline_cuantil (v2)
│   ├── interpretacion.py         # traducción en lenguaje directo, por reglas fijas
│   └── router.py                 # POST /api/predict
├── schemas/prediccion.py         # Pydantic request/response
└── tests/                        # ver "Pruebas"
```

## Contrato del endpoint

`POST /api/predict`
```json
// request: producto por codigo_item o id_producto, sucursal por nombre o id_sucursal
{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}
{"id_producto": 91, "id_sucursal": 1, "horizonte": 15, "fecha_corte": "2025-12-12"}
```
- `fecha_corte` (opcional): fecha de los datos con que se predice. Por
  defecto, el último día con ventas en la bodega; una fecha anterior
  reproduce lo que el modelo habría dicho ese día.
- `200`: ver `schemas/prediccion.py::PrediccionResponse` (`fecha_features` =
  fecha de los datos usada).
- `404`: producto o sucursal inexistentes, o par sin historia suficiente
  (mismo criterio de cold start que `07`: al menos 30 días con venta y 30
  días hábiles de historia; no se inventa una predicción).
- `422`: `horizonte != 15`, sucursal no física (`SIN_SUCURSAL`,
  `BODEGA_CENTRAL`: el modelo solo se entrenó con PRINCIPAL, LA 21 y
  GLORIETA), `fecha_corte` posterior al último dato o sin identificadores.
- `503`: bodega no disponible, vacía, o `dim_tiempo` sin días hábiles
  suficientes para el horizonte.

`GET /api/health` → `{"status": "ok"|"degradado", "service": ..., "modelos_cargados": [...], "bodega": "ok"|"sin conexión"}`.
OpenAPI en `/api/docs` / `/api/openapi.json`. Cada campo de entrada y salida
de los endpoints está explicado en [`ML-SERVICE-API.md`](ML-SERVICE-API.md).

## Cómo correr (sin Docker)

```bash
cd ml_service
python3 -m venv --system-site-packages .venv   # reusa pandas/lightgbm/scikit-learn del env etl
./.venv/bin/pip install -r requirements.txt
export POSTGRES_HOST=localhost POSTGRES_PORT=5432   # donde esté la bodega cargada
./.venv/bin/python3 -m pytest --cov=. --cov-report=term-missing
./.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
```

Con Docker Compose y desde cero (bodega incluida): `docs/AMBIENTE-DESARROLLO.md`.

## Verificación del fix (bodega en Postgres)

Contra Postgres 16 (imagen del `docker-compose.yml`) con la bodega cargada
por `etl_real/cargar_postgres.py` y verificada con `database/test-dw-real.SQL`:

- **Paridad con el entrenamiento**: en 82 pares (80 al azar + `P1632` en
  PRINCIPAL y GLORIETA) y todos sus orígenes de la matriz (3.325 filas, los 5
  folds), las 14 features calculadas desde la bodega coinciden con
  `matriz_as_of.parquet` y las predicciones son idénticas. Para lograrlo se
  replica la precisión `float32` de `07` (un CV² calculado en `float64`
  difería en el último bit y cambiaba de lado un corte de árbol en 3 filas).
- **Contraste con la demanda real**: con `fecha_corte` 60 días hábiles antes
  del último dato, la mediana de predicción/demanda real de los 15 días
  siguientes está entre 0,2 y 5 en cada rama (cota de sanidad, no evaluación).
- **Ejemplo**: `P1632|PRINCIPAL` a 2025-12-31 → rama `intermitente`,
  `q50=3366`, límite superior `4609`; a `fecha_corte=2025-12-12`, `q50=3206`
  (el mismo valor de la matriz). Unos 60 ms por petición (la primera carga el
  calendario, ~200 ms).
- **Tests**: 53, todos pasan (49 sin bodega; los 4 de integración se saltan
  sin conexión), cobertura 96%.

## Pendiente / fuera de alcance de esta HU

1. Integración con el frontend/agente NLP que consuma este endpoint, y
   alertas de `api/` que usen la predicción (Nivel 2: stock vs. cuantil de
   negocio).
2. Construir/correr el contenedor con Docker Compose en una máquina con
   Docker (`docs/AMBIENTE-DESARROLLO.md`).
3. En un reentrenamiento: revisar `frecuencia_as_of` (acumulada, crece con el
   tiempo) y la definición de los tramos del mes del factor de calendario
   (`07` usa día 15/último día y todos los meses; la regresión de `03` los
   estimó con días 15-17 y solo meses ordinarios). Se conservaron tal cual
   por paridad con los modelos entrenados.
