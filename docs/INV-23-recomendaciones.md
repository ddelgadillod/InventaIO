# INV-23 — Endpoints de recomendaciones en el Core API

El Core API (`api/`, puerto 8000) expone dos GET que leen las recomendaciones
de compras (INV-21) y de transferencias (INV-22) de `ml_service`, las filtran
por sucursal, categoría y urgencia, les agregan el nombre y la categoría del
producto y recalculan el resumen sobre lo filtrado. El frontend y el agente ya
no necesitan conocer el contrato POST de `ml_service`.

La especificación, con las decisiones C1–C6, las reglas R1–R6 y por qué se
apartan del borrador, está en
[`INV-23-requerimientos.md`](INV-23-requerimientos.md). Este documento dice
cómo quedó implementado y qué dio con los datos reales.

## Cómo se usa

Los dos endpoints exigen el token de `POST /api/auth/login`.

```powershell
$t = (Invoke-RestMethod http://localhost:8000/api/auth/login -Method Post -ContentType "application/json" `
  -Body '{"email":"gerente@inventaio.co","password":"admin123"}').access_token
$H = @{Authorization = "Bearer $t"}

Invoke-RestMethod "http://localhost:8000/api/ml/recomendaciones/compras?sucursal=PRINCIPAL&incluir_detalle=false" -Headers $H
Invoke-RestMethod "http://localhost:8000/api/ml/recomendaciones/transferencias?sucursal=LA%2021&urgencia=urgente" -Headers $H
```

PowerShell 5.1 decodifica mal el UTF-8 de la respuesta: "Lácteos" se ve como
`LÃ¡cteos`. Es un problema de la consola, no del servicio; con `curl`, Python
o el Swagger (http://localhost:8000/api/docs) los acentos se ven bien.

| Parámetro | Endpoints | Regla |
| --- | --- | --- |
| `sucursal` | Los dos | PRINCIPAL, LA 21, GLORIETA o BODEGA_CENTRAL, sin distinguir mayúsculas ni acentos. En compras, una sucursal física trae sus compras directas y las de la Bodega donde participa, vistas desde ella (R1). En transferencias, los traslados con esa sucursal como origen o destino |
| `categoria` | Los dos | Una de las 33 categorías de `dw.dim_producto`, sin distinguir mayúsculas ni acentos (`lacteos`) |
| `urgencia` | Los dos | `urgente`, `alta` o `normal`; en transferencias, también `vigilancia`. No filtra las alertas |
| `incluir_detalle` | Compras | `true` por defecto. Con `false` no llega el cálculo por sucursal |
| `incluir_balance` | Transferencias | `false` por defecto. Con `true` llegan el balance y las alertas `sin_pronostico` |

| Rol | Sin `sucursal` | Con `sucursal=X` |
| --- | --- | --- |
| `gerente`, `admin_bodega` | Todo | X |
| `admin_sucursal` | Su sucursal (`filtros_aplicados.sucursal_por_rol = true`) | X si es la suya; si no, 403 |

Errores: 401 token inválido; 403 sin token o con una sucursal ajena; 409 la
foto es posterior a la última venta (el detalle de `ml_service`); 422
parámetro inválido o desconocido; 502 error inesperado de `ml_service`; 503
`ml_service` o la bodega no disponibles; 504 `ml_service` no respondió en
120 s.

## Cómo quedó

| Archivo | Qué hace |
| --- | --- |
| `api/ml/router.py` | Los dos GET: valida y normaliza los filtros, aplica los permisos por rol, pide el resultado (de la caché o de `ml_service`) y lo filtra |
| `api/ml/cliente.py` | `ClienteML`: `GET /api/health`, `POST /api/compras` y `POST /api/transferencias` con `httpx`, y la traducción de errores. INV-25 lo reutiliza |
| `api/ml/cache.py` | `CacheRecomendaciones`: en memoria, con clave, TTL y un candado por clave |
| `api/ml/catalogo.py` | Productos, categorías y sucursales de `dw`, y la normalización de los filtros |
| `api/ml/filtros.py` | Enriquecimiento, filtros, vista desde la sucursal y resumen. Funciones puras, sin I/O |
| `api/schemas/recomendaciones.py` | Esquemas de respuesta; también documentan el Swagger |

**Una petición**, paso a paso:

1. `get_current_user` valida el token.
2. `resolver_filtros` normaliza `sucursal` y `categoria` contra la bodega (422 si no existen) y aplica el rol.
3. `ClienteML.salud()` lee la fecha de la foto y las versiones de políticas de `ml_service` (503 si está degradado o sin foto).
4. Con la clave `(endpoint, foto, versión y fecha de INV-21, versión y fecha de INV-22)`, la caché devuelve el resultado guardado o llama al POST completo (compras con detalle, transferencias con balance), le agrega nombre y categoría y lo guarda.
5. `filtrar_compras` o `filtrar_transferencias` arman la respuesta con copias de las filas, sin tocar lo guardado, y calculan el resumen.

### Decisiones de implementación

Donde la especificación deja margen, se decidió así. Cada punto tiene su prueba.

| Tema | Decisión | Por qué |
| --- | --- | --- |
| Orden de las validaciones | Primero el token, después la sucursal desconocida (422) y luego el permiso (403) | Un error de digitación se informa como tal, también a un `admin_sucursal` |
| `admin_sucursal` sin sucursal, o con SIN_SUCURSAL | 403 "El usuario no tiene una sucursal asignada" | No hay una sucursal válida que aplicarle |
| Qué se guarda en la caché | La respuesta completa y enriquecida: compras con detalle y transferencias con balance | Un solo cálculo sirve para todos los filtros y para `incluir_detalle` / `incluir_balance` |
| Clave de la caché | Versión **y fecha** de las dos políticas, en los dos endpoints | Si se cambia el JSON sin subir la versión, la fecha también cambia la clave. Un cambio en INV-21 recalcula también transferencias: es raro y más simple |
| Claves viejas | Al guardar una clave nueva de un endpoint se descarta la anterior | Una foto nueva no deja la anterior ocupando memoria |
| Error de `ml_service` | No se guarda; la siguiente petición lo vuelve a intentar | Se recupera sin reiniciar la API |
| `ml_service` responde 422 | 502 | El Core API arma el cuerpo: un 422 sería un error del Core API, no del usuario |
| `calculado_en` | UTC, con `Z` | Sin ambigüedad de zona horaria |
| `api/.dockerignore` | Excluye `.venv/`, cachés y cobertura | El build desde Windows fallaba: `api/.venv` es un entorno de Linux con enlaces que Windows no lee |

## Cambio en `ml_service`

`GET /api/health` agrega `fecha_inventario` (nula sin bodega o sin foto) y
`politicas` (`inv21` e `inv22`, con versión y fecha). Los demás campos y los
otros endpoints no cambian. Detalle en [`ML-SERVICE-API.md`](ML-SERVICE-API.md).

## Resultados con los datos reales (foto al 2025-12-31)

Confirman los "Resultados esperados" de la especificación. Medido con Docker
Compose (`postgres`, `ml-service` y `api`) y `curl`.

| Consulta | Resultado |
| --- | --- |
| Compras sin filtros | 1.340 líneas (449 + 891); 41.952 unidades y 3.169 kg; 277 en `cubrir_con_traslado`; 220 alertas; 1.411 productos. Igual que `ml_service` |
| Compras de PRINCIPAL | 814 líneas (164 + 650); necesidad vía Bodega 19.637,39; 172 en `cubrir_con_traslado`; 95 alertas. P1632 "HUEVOS *UND" compra 4.735; el agua 00008, urgente en `ml_service`, es normal desde PRINCIPAL (36,95 de 46,86) |
| Compras de GLORIETA, arroz, urgente | P1938 (4) y P4570 (20), para la Bodega |
| `admin.sur` sin sucursal | GLORIETA por rol: 562 líneas. Con `sucursal=PRINCIPAL`, 403 |
| Transferencias sin filtros | 119 traslados (4.623 unidades); 11.710 filas de balance; déficit 20.677,18 (unidades + kg); 220 alertas listadas y 2.762 `sin_pronostico` contadas; 4.419 productos |
| Transferencias de LA 21 | 10 traslados; 40 alertas; 697 `sin_pronostico` |
| Transferencias de arroz | P3937: 572 a GLORIETA y 695 a PRINCIPAL |

**Tiempos.** Con la caché vacía, la primera llamada tarda lo que tarda
`ml_service`: unos 22 s compras y unos 20 s transferencias con balance. Con
la caché caliente:

| Respuesta | Tiempo | Tamaño |
| --- | --- | --- |
| Transferencias sin balance | 0,04 s | 0,1 MB |
| Transferencias con balance, sin filtros | 0,50 s | 6,4 MB |
| Transferencias con balance, LA 21 | 0,09 s | 1,2 MB |
| Compras con detalle, sin filtros | 0,08 s | 1,2 MB |
| Compras de PRINCIPAL con detalle | 0,11 s | 0,7 MB |

Invoke-RestMethod de PowerShell 5.1 tarda varios segundos más en leer las
respuestas grandes; el tiempo es de la consola, no del servidor.

## Pruebas

Corren dentro del contenedor `api` (Python 3.11, las dependencias de la imagen):

```powershell
docker compose up -d --build ml-service api
docker compose exec api pytest -m "not integracion" --cov=ml   # unitarias, unos 5 s
docker compose exec api pytest -m integracion                   # contra los servicios reales, unos 50 s
docker compose exec api ruff check .
```

| Archivo | Pruebas | Qué cubre |
| --- | --- | --- |
| `test_recomendaciones_compras.py` | 23 | Sin filtros contra `ml_service`, vista desde la sucursal, Bodega, categoría normalizada, kilos, urgencia y alertas, combinaciones, sin detalle, producto sin `dim_producto`, 422 |
| `test_recomendaciones_transferencias.py` | 12 | Balance opcional, origen o destino, Bodega, vigilancia, urgencia nula, categoría, combinaciones, 422 |
| `test_recomendaciones_permisos.py` | 11 | Sin token, token inválido y los tres roles en los dos endpoints |
| `test_recomendaciones_cache_errores.py` | 19 | Caché (clave, foto y políticas nuevas, TTL, concurrencia, errores no guardados) y la traducción de cada error de `ml_service` |
| `test_recomendaciones_integracion.py` | 5 | Las cifras de arriba con `ml_service`, Postgres y los usuarios de prueba; caché caliente en menos de 1 s |

`conftest.py` reemplaza el usuario, el catálogo y `ml_service` (un
`httpx.MockTransport` con respuestas de la forma real), así que las
unitarias no necesitan servicios. Resultado: 70 pruebas pasan; cobertura de
`api/ml/` del 96 % con las unitarias y del 100 % con la integración (la
lectura de `dw` del catálogo solo la ejercita la integración). `ruff`, sin
observaciones. En `ml_service`, 189 pruebas pasan y 1 se salta, con las dos
nuevas de `/api/health`.

**De punta a punta por HTTP**, como los scripts de las otras historias del
Core API: `bash api/tests/test_recomendaciones.sh` (desde Ubuntu/WSL, con
`curl` y `jq`). Son 54 comprobaciones contra los contenedores: los resultados
de arriba, los 422, los permisos con los cuatro usuarios, la caché y la
regresión de `ml_service`. Tarda unos 45 s, casi todo en calentar la caché.

El CI no cambia: sigue corriendo `ruff check api/` y el build del frontend.

## Criterios de aceptación

| # | Criterio | Dónde se verifica |
| --- | --- | --- |
| 1 | Compras con todos los campos, nombre y categoría, filtros, `calculado_en` y resumen propio | `test_sin_filtros_devuelve_lo_de_ml_service_enriquecido`, integración |
| 2 | Transferencias igual, con balance opcional | `test_sin_filtros_sin_balance_...`, `test_con_balance_...` |
| 3 | Token y permisos por rol (C1) | `test_recomendaciones_permisos.py`, `test_permisos_con_usuarios_reales` |
| 4 | Compras por sucursal con la vista desde ella (C2, R1) | `test_sucursal_fisica_...`, `test_la_urgencia_de_una_compra_de_la_bodega_...`, `test_compras_desde_principal` |
| 5 | Transferencias por origen o destino | `test_sucursal_filtra_traslados_por_origen_o_destino` |
| 6 | Normalización, 422 y combinaciones vacías (R3) | `test_categoria_sin_mayusculas_ni_acentos`, `test_parametros_invalidos_dan_422`, `test_combinacion_valida_sin_filas_...` |
| 7 | Urgencia por endpoint, sin filtrar alertas (R2) | `test_la_urgencia_no_filtra_las_alertas`, `test_urgencia_vigilancia_...`, `test_la_urgencia_nula_no_pasa_el_filtro` |
| 8 | Filtros opcionales y AND; sin filtros, los totales de `ml_service` (R4) | `test_tres_filtros_combinados`, pruebas sin filtros e integración |
| 9 | El resumen cuadra con las filas devueltas | Resúmenes completos comparados en escenarios con y sin filtros |
| 10 | Caché (C3) | `test_la_segunda_llamada_...`, `test_foto_o_politicas_nuevas_...`, `test_la_cache_caliente_...` |
| 11 | Errores de `ml_service` (R5) | `test_errores_de_ml_service_se_traducen_y_no_se_guardan` y vecinas |
| 12 | `ml_service` solo cambia en `/api/health` | Sus 189 pruebas pasan; `/api/predict` sigue dando 3.366,01 para P1632 en PRINCIPAL |
| 13 | Swagger documentado | http://localhost:8000/api/docs, etiqueta "Recomendaciones": los dos GET, sus parámetros opcionales con los valores permitidos y los esquemas de respuesta |

## Limitaciones y pendientes

- **Primera llamada lenta** (20–22 s) después de cada reinicio de la API, de un `--reload` en desarrollo o de una foto nueva. El frontend debe esperar al menos 60 s.
- **Caché por proceso**: con varios workers, cada uno calcularía la suya. Hoy la API corre con uno.
- **Memoria**: la caché guarda unos 8 MB de JSON, varias veces eso como objetos de Python.
- **Contratos acoplados**: si cambia el contrato de `ml_service`, los esquemas del Core API fallan con 500. La prueba de integración lo detecta.
- **Usuarios de prueba**: la verificación necesita el seed de usuarios en la base local, que no está en el repo.
- Pendientes de confirmar (filtro por producto o por rama, refresco manual de la caché, paginación): siguen con los valores por defecto de la especificación.
