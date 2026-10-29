# Preregistro del holdout 2026 (Nivel 1)

**Fecha:** 2026-09-25, antes de disponer de ventas de 2026. **Estado:** preregistrado; ningún dato de 2026 fue visto.
Fuente de verdad: `notebooks/preregistro_holdout_2026.json` (este documento lo explica). Registro en MLflow: experimento
`EDA-fix-nivel1-16-holdout-2026`, run `preregistro_v1`, creado por `notebooks/registrar_preregistro_2026.py`.

> **Fe de erratas (2026-10-08):** el commit `a340983` de la tabla «Qué queda congelado» no existe en el historial publicado. Lo congelado se verifica por huella (SHA-256); ver «Fe de erratas» al final. Las reglas, los datos y los modelos no cambian.

## Por qué

Todas las evaluaciones de Nivel 1 hasta hoy (09-15, walk-forward con purge) usan datos que también sirvieron para diseñar
features, elegir la política y calibrar; el fold 5 no es un holdout virgen. Además, la calibración conformal por estrato de
la rama intermitente se activó por decisión del usuario sin cumplir la regla de 14. Las ventas posteriores a 2025-12-31 son el
primer holdout limpio. Fijar aquí las reglas antes de ver esos datos evita ajustarlas a posteriori.

## Qué queda congelado

| Qué | Valor |
|---|---|
| Commit | `a340983` (`models/` idéntico a ese commit) |
| Modelos | `models/nivel1_{intermitente,suave_no_perecedero,suave_perecedero}.joblib` + `nivel1_metadata.json`, con SHA-256 en el JSON; copia en el run como artefactos `modelos_congelados/` |
| Política | intermitente = `relativo` con calibración por estrato; suaves = `baseline_cuantil` |
| Estratos | los del paquete (corte 2025-12-31: 218 cabeza / 1.270 medio / 9.647 cola); no se recalculan con 2026 |
| Matriz de entrenamiento | `matriz_as_of.parquet` hash `8f2d656df51a` |
| Referencia de R2 | `baseline_cuantil` de la rama intermitente (media móvil × cuantil empírico de la razón por estrato), estimada con los mismos datos y estratos; cifras en el JSON y paquete en `referencia/` del run |

Hasta emitir el veredicto: no se reentrena, no se buscan hiperparámetros, y no cambian features, estratos, offsets ni razones.

## Diseño de la evaluación

- **Compuerta de datos:** las ventas 2026 pasan por el mismo ETL sin cambios de lógica (un formato de fila nuevo se agrega como
  formato E). Se revisan discrepancias, duplicados y calidad sin descartar nada en silencio. Los productos nuevos se categorizan a
  mano. Las filas de la matriz con origen ≤ 2025-12-12 deben quedar idénticas a las de la matriz congelada.
- **Orígenes:** primer día hábil de 2026 y luego cada 15 días hábiles, mientras la ventana objetivo esté completa. La rejilla es
  mecánica. **Mínimo 8 orígenes** para un veredicto (con 6 meses se esperan ~11); con menos, el resultado es un *indicio* y no
  activa acciones.
- **Universo principal:** pares con estrato en el paquete congelado, con las mismas exclusiones y la misma asignación de rama as-of.
  Los pares nuevos (arranque en frío) y los orígenes de diciembre de 2025 cuya ventana cae en 2026 se reportan aparte, sin decisión.
- **Predicción:** la del motor de `ml_service` en el commit congelado. Una versión vectorizada solo vale si coincide con el motor
  en ≥ 1.000 filas.
- **Incertidumbre:** IC95 por bootstrap de productos (B=2000, semilla 0), con las funciones de `evaluar_nivel1.py`.

## Reglas

| Regla | Rama | Criterio | Si no se cumple |
|---|---|---|---|
| **R1** precisión | intermitente | Mejora del WAPE del q50 frente a la media móvil con IC95 > 0 | No confirmada; se reevalúa en el reentrenamiento (paso 20) |
| **R2** costo | intermitente | Mejora del costo Cu/Co (0,25/0,03) del cuantil de negocio frente a la referencia congelada con IC95 > 0 | IC que cruza 0: se mantiene, marcada no confirmada. IC entero < 0: la rama pasa a `baseline_cuantil` |
| **R3** calibración | las tres | \|cobertura − alpha\| ≤ 0,05 en la rama y en cada estrato con ≥ 200 filas | Se reestiman offsets (intermitente) o razones (suaves) con 2026, sin tocar el modelo |
| **R4** calibración por estrato | intermitente | Frente a la misma predicción sin offset: cobertura más cercana a 0,893 en ≥ 2 de 3 estratos y costo no peor con IC95 | Se desactiva (equivale a `--sin-calibracion`) |

**Veredicto global:** *política confirmada* si se cumplen R1-R4. Si alguna falla, se aplica la acción de esa regla. Son 4 reglas
sin corrección por comparaciones múltiples; queda declarado aquí.

## Qué se espera (solo contexto, no son criterios)

Resultados walk-forward con purge (folds 2-5):

- R1: +5,1% [+4,5; +5,8].
- R2: +6,9% [+5,4; +9,2] sin calibración.
- R3: cobertura de intermitente con calibración 0,895 / 0,901 / 0,906; suaves 0,905 (objetivo 0,893) y 0,169 (objetivo 0,167).
- R4: la calibración no mejoró el costo (+0,06% [−1,1; +1,0] en los folds 2-4; −3,5% en el fold 5).

El offset de la cabeza varió entre 0,11 y 0,25 según el periodo, frente a +0,041 en la exportación. Es el punto con más riesgo
de no cumplir R3.

## Desviaciones

Ninguna. Cualquier cambio posterior se agrega al campo `desviaciones` del JSON con fecha y motivo, se reporta junto al
resultado y, si cambia reglas, se registra como `preregistro_v2` sin borrar la v1.

## Fe de erratas

**8 de octubre de 2026.** Corrección editorial: no cambia reglas, datos, modelos ni criterios, así que no es una desviación. El JSON y el run
`preregistro_v1` de MLflow no se modificaron.

1. **El commit `a340983` no se encuentra.** No está en el historial de GitHub (la API responde «No commit found for SHA»), ni en el clon de
   trabajo, ni en la copia anterior de Windows. No se sabe qué pasó con él; lo más probable es un commit local reescrito (rebase o amend)
   antes de publicarse. La referencia no sirve para reconstruir lo congelado.
2. **Lo congelado se verifica por huella, no por commit.** Los SHA-256 de `congelado.archivos_sha256` en
   `notebooks/preregistro_holdout_2026.json` coinciden con los archivos de `models/` y con `models/SHA256SUMS` (agregado en INV-24):

   | Archivo | SHA-256 |
   |---|---|
   | `models/nivel1_intermitente.joblib` | `937b4231b5e51c444471c414784ed05b5aaf303746bd5f1f86055049a768faed` |
   | `models/nivel1_suave_no_perecedero.joblib` | `55883ab323b6f74357fe976a943b99482cbb23509f6af860cde050dcb18851ea` |
   | `models/nivel1_suave_perecedero.joblib` | `38dd79458a34772d187f996642e363b55ad3181f8f44963de9116a6a9a618c08` |
   | `models/nivel1_metadata.json` | `06d0cfdcbdb319cf609283f0148cec6e8318d53725d6d5f56a46b3040e2671f0` |

   Los cuatro entraron al repositorio en el commit `e7bfe50` (2026-09-29) y no han cambiado desde entonces
   (`git log -- models/nivel1_intermitente.joblib`). Se comprueban con `cd models && sha256sum -c SHA256SUMS`, que también corre el CI.
3. **`models/` ya no es idéntico en su totalidad.** Desde el 29 de septiembre tiene un archivo más, `nivel1_parametros_features.json`
   (commit `6f4768b`, INV-20, con los parámetros para calcular las features en el servicio). No forma parte de lo congelado; los cuatro
   archivos congelados siguen idénticos.
4. **Qué prueba la fecha.** El historial de Git solo prueba que este documento y los modelos entraron al repositorio el 29 de septiembre
   (commit `e7bfe50`). La fecha del 25 de septiembre se apoya en `fecha_generacion` de `models/nivel1_metadata.json`
   (2026-09-25T01:30:56 UTC) y en el run `preregistro_v1` de MLflow, que no se pudo consultar al escribir esta fe de erratas: quien evalúe el
   prerregistro debe comprobar ese run.
