# INV-63 · Holdout 2026 de los modelos de Nivel 1: resultado y decisión

**Fecha:** 17-nov-2026 · **Veredicto:** política confirmada (R1, R2, R3 y R4 se cumplen con 18 orígenes) · **Acción:** ninguna; el paquete
congelado sigue en producción sin cambios. **Exploración (§8):** ninguna receta nueva superó al paquete en la confirmación; se mantiene la
receta vigente.

- Reglas y paquete: `docs/PREREGISTRO-HOLDOUT-2026.md` y `notebooks/preregistro_holdout_2026.json` (preregistro del 25-sep-2026, con las
  desviaciones D1 y D2 registradas el 17-nov antes de evaluar).
- Requerimientos: `docs/INV-63-requerimientos.md`.
- Evaluación: `notebooks/16_holdout_2026.py` (orquestador) y `notebooks/holdout_2026.py` (reglas, con pruebas sintéticas en
  `notebooks/tests/test_holdout_2026.py`).
- MLflow: experimento `EDA-fix-nivel1-16-holdout-2026`, run `evaluacion_holdout_2026` (`80d95f0b166449bd81c56c5610034a13`, intento 1,
  commit `cdc366b`).

## 1. Problema

El motor de pronóstico de Nivel 1 se diseñó y se validó con walk-forward sobre 2022-2025. Esos datos ya sirvieron para elegir modelos,
hiperparámetros y calibración, así que sus cifras no son un desempeño limpio. Faltaba saber si la política desplegada se sostiene con datos que
nadie había visto:

- rama intermitente: modelo `relativo` con calibración conformal por estrato;
- ramas suaves: `baseline_cuantil`.

Las ventas de enero a septiembre de 2026 son el primer holdout limpio. El preregistro fijó, antes de verlas, cuatro reglas y la acción que
dispara cada una si no se cumple.

## 2. Datos y método

| Aspecto | Qué se hizo |
|---|---|
| Ventas 2026 | Excel diarios de enero a septiembre, convertidos con el parser de ventas2 ajustado como formato E (sin tocar A-D) y cargados con el mismo ETL en un DW paralelo. El DW del stack no se tocó. |
| Compuertas | SHA-256 del paquete (`models/SHA256SUMS` y el preregistro); serie diaria neta 2022-2025 idéntica a la del DW vigente (1.804.732 registros, 1.362 días hábiles, huella `82d3a820b3d9`); fotos de inventario con los conteos que midió D1. El orquestador se detiene si alguna falla. |
| Universo (D1) | Pares del paquete cuyo producto está en las fotos de inventario del 31-dic-2025 y del 30-sep-2026: 10.882 de 11.135 pares (4.451 productos). El universo preregistrado (v1) se reporta como sensibilidad. |
| Orígenes | Primer día hábil de 2026 y luego cada 15 días hábiles con la ventana completa: 18 orígenes, del 2026-01-02 al 2026-09-15. Ninguna ventana salta un bloque sin datos (control de empalme de 07). |
| Features (D2) | `ml_service/prediccion/features.py` con los parámetros congelados, estáticas a la fecha de cada origen, como el servicio. |
| Predicción | `ml_service/prediccion/motor.py::predecir_lote`, el motor congelado. En una muestra de 1.000 filas coincide exactamente con `predecir` fila a fila (diferencia máxima 0). |
| Incertidumbre | IC95 por bootstrap de productos (B = 2000, semilla 0), con `notebooks/evaluar_nivel1.py`. |

Filas evaluadas en D1: 126.693 (intermitente 125.369, suave no perecedera 788, suave perecedera 536). Los pares sin historia suficiente a la
fecha del origen (menos de 30 días con venta) no se predicen, igual que en el servicio.

## 3. Resultado de las reglas

| Regla | Qué mide | Criterio | D1 (decide) | v1 (sensibilidad) | Estado |
|---|---|---|---|---|---|
| R1 · Precisión | WAPE del q50 de la rama intermitente frente a la media móvil | Mejora con IC95 > 0 | +6,1 % [+4,9; +7,4] | +6,1 % [+4,9; +7,3] | Confirmada |
| R2 · Costo | Costo Cu/Co del cuantil de negocio intermitente frente a la referencia `baseline_cuantil` congelada | Mejora con IC95 > 0 | +7,0 % [+5,3; +9,0] | +7,0 % [+5,4; +9,2] | Confirmada |
| R3 · Calibración | \|cobertura − alpha\| en cada rama y en cada estrato con ≥ 200 filas | ≤ 0,05 | Las 3 ramas y los 6 estratos evaluables cumplen | Igual | Confirmada |
| R4 · Calibración por estrato | Calibración conformal frente a la misma predicción sin offset | Más cerca de 0,893 en ≥ 2 de 3 estratos y costo no peor | 3 de 3 más cerca; costo +0,04 % [−0,13; +0,21] | Igual | Confirmada |

**Coberturas (R3, D1).** La cobertura es la fracción de filas con la demanda real ≤ cuantil de negocio.

| Rama | Alpha | Rama completa | Cabeza | Medio | Cola |
|---|---|---|---|---|---|
| Intermitente | 0,893 | 0,901 (125.369 filas) | 0,877 (2.992) | 0,900 (22.453) | 0,902 (99.924) |
| Suave no perecedera | 0,893 | 0,920 (788) | 0,923 (531) | 0,914 (257) | sin filas |
| Suave perecedera | 0,167 | 0,194 (536) | 0,190 (401) | insuficiente (114) | insuficiente (21) |

**R4 por estrato (D1).** Coberturas con calibración y sin ella:

| Estrato | Con calibración | Sin calibración |
|---|---|---|
| Cabeza | 0,877 | 0,858 |
| Medio | 0,900 | 0,881 |
| Cola | 0,902 | 0,905 |

**Frente a lo esperado.** El walk-forward del preregistro, que no era criterio, anticipaba R1 +5,1 %, R2 +6,9 % y coberturas de
0,895 / 0,901 / 0,906. El holdout queda en el mismo orden: no hay señal de sobreajuste al periodo de diseño.

## 4. Análisis secundarios (sin decisión)

Son los que pide el preregistro y la ficha. Se reportan para INV-62 y no cambian el veredicto. Tablas completas en el run de MLflow
(`tablas/`).

- **Estabilidad por origen.**
  - R1: el IC queda por encima de 0 en 12 de los 18 orígenes, cruza 0 en 4 y queda por debajo en 2 (2026-01-02: −8,5 %; 2026-03-03:
    −8,6 %).
  - R2: el IC queda por encima de 0 en 12, cruza 0 en 5 y queda por debajo solo en el 2026-01-02 (−9,0 %).
  - El origen del 2 de enero proyecta la demanda de diciembre sobre la primera quincena del año. Es un efecto de calendario que el paquete
    congelado no corrige del todo; queda como insumo para INV-62.
- **Por mes.** El WAPE mejora en todos los meses menos marzo (−2,8 %). El costo mejora en todos.
- **WAPE por estrato (intermitente).** Cabeza +3,7 % [−0,2; +7,8], con IC que cruza 0; medio +5,4 % [+4,1; +6,7]; cola +8,3 % [+7,7;
  +8,9].
- **Sin el peor producto.** R1 +6,4 % [+5,4; +7,5] y R2 +7,4 % [+5,9; +9,5]: el resultado no depende de un producto.
- **Pares nuevos** (sin estrato en el paquete, con historia suficiente durante 2026): 32 pares y 214 filas. Mejora +3,7 % [−1,7; +6,9] y
  cobertura 0,874. Son pocos para decidir.
- **Orígenes de diciembre de 2025.** Es un solo origen (2025-12-27), con la ventana en enero de 2026.
  - R1: +3,7 % [−1,7; +8,2].
  - R2: +5,7 % [−5,5; +17,1].
  - Las ramas suaves quedan fuera de tolerancia, con 1 origen y menos de 60 filas por rama.
- **Sesgo del q50.** En la rama intermitente la suma de las medianas queda 8,2 % por debajo de la venta real (cola −14,7 %). Es lo esperado
  al sumar medianas de una demanda sesgada a la derecha; no es un defecto del cuantil de negocio, que cumple R3.
- **Señales de stock.** Las fotos se agregan por producto y ubicación, con todas las ubicaciones, como en `fact_inventario`.

  | Grupo | Pares evaluados | WAPE modelo | WAPE media móvil | Cobertura | Sesgo q50 |
  |---|---|---|---|---|---|
  | Stock ≤ 0 al 31-dic-2025 (1.158 pares en la foto) | 350 | 0,497 | 0,550 | 0,879 | −8,8 % |
  | Stock > 0 al 31-dic-2025 | 6.905 | 0,363 | 0,384 | 0,899 | −5,9 % |
  | Negativo en las dos fotos (149) | 76 | 0,572 | 0,608 | 0,893 | −15,3 % |
  | Negativo solo en dic-2025 (86) | 68 | 0,414 | 0,472 | 0,881 | −2,5 % |
  | Negativo solo en sep-2026 (217) | 140 | 0,468 | 0,510 | 0,860 | −9,8 % |
  | Sin negativo | 6.971 | 0,360 | 0,380 | 0,899 | −5,8 % |

  Los pares con stock ≤ 0 o negativo tienen más error, aunque el modelo sigue superando a la media móvil. El negativo persistente
  subestima más (−15 %), lo que apunta a demanda censurada o a errores de catálogo. Son el insumo de la máscara de demanda censurada de
  INV-62.

  Los conteos preliminares de la ficha (79 pares solo en dic y 165 solo en sep) usaban otra agregación. Los de esta tabla son los del
  orquestador; si se cuentan solo los tres almacenes de venta, salen 144 / 76 / 200.

## 5. Decisión

- **Problema.** Confirmar o ajustar, con datos no vistos, la política del motor que se despliega.
- **Alternativas.**
  1. Mantener la política tal como está.
  2. Aplicar las acciones de las reglas que fallaran: pasar la rama intermitente a `baseline_cuantil` (R2), reestimar offsets o razones
     con 2026 (R3) o desactivar la calibración por estrato (R4).
  3. Recalibrar igualmente con 2026 aunque las reglas se cumplan.
- **Decisión.** Alternativa 1: el paquete congelado del 25-sep-2026 sigue en producción sin cambios de modelos, offsets, razones ni
  código.
- **Justificación.**
  - Las cuatro reglas se cumplen en el universo que decide (D1) y en el preregistrado (v1), con 18 orígenes, más del doble del mínimo
    de 8.
  - Ninguna acción se activa.
  - La alternativa 3 violaría el compromiso del preregistro de no tocar el paquete por un resultado que cumple.
  - La recalibración es parte del reentrenamiento (INV-62), con estas mismas reglas como vara.
- **Impacto.**
  - `ml_service` no cambia: mismo paquete, mismas huellas y mismo comportamiento del servicio.
  - La política queda validada fuera de muestra para la propuesta de nube.
  - INV-62 hereda el paquete congelado como referencia: un modelo reentrenado debe superarlo con las mismas reglas.
  - La operación con datos al 30-sep-2026 (CA 8) recarga los datos, no el modelo.

**Cautelas para INV-62** (observaciones, no acciones):

- La cobertura de la cabeza (0,877) cumple la tolerancia pero queda 1,6 puntos por debajo de 0,893. Era la duda que dejó
  `docs/FIX-EDA-MODELADO-NIVEL1.md`, por la inestabilidad del offset de la cabeza.
- El aporte de la calibración por estrato es de cobertura, no de costo (+0,04 %, con IC que cruza 0).
- El inicio de año y marzo son los periodos más débiles.
- Las ramas suaves tienen pocas filas (788 y 536), así que sus IC son anchos.
- Son 4 reglas sin corrección por comparaciones múltiples, como declara el preregistro.

## 6. Trazabilidad

| Elemento | Dónde está |
|---|---|
| Modelos (entrenamiento y exportación, INV-17 v2, 25-sep-2026) | Servidor segovia, MLflow, experimento `INV-17-inventaio-modelos-produccion-v2`: runs `2a6a5f2118ff4da28d4d390a5eb734ff` (intermitente), `8d78a8d34fbc4e1ab0186e4205669251` (suave no perecedera) y `0575fad2b7114d45b966f3a2e9356dfd` (suave perecedera). Los archivos se verifican por SHA-256 en `models/SHA256SUMS`. |
| Preregistro | Servidor segovia, MLflow, experimento `EDA-fix-nivel1-16-holdout-2026`, run `preregistro_v1`. |
| Evaluación | MLflow local, mismo experimento, run `evaluacion_holdout_2026`, con etiquetas que apuntan a los runs de segovia, las desviaciones D1 y D2, el commit congelado y el de la evaluación, y las huellas del DW, las fotos y el parser. |
| Filas evaluadas | `data/processed_real/holdout_2026/` del DW paralelo, fuera de git (datos del negocio). |

**Pendiente en segovia** (no cambia el veredicto; se documenta cuando el servidor esté disponible):

1. Comprobar el run `preregistro_v1`: fecha y artefactos (punto 4 de la fe de erratas del preregistro).
2. Repetir la paridad de `features.py` con la matriz congelada (`8f2d656df51a`).
3. Correr la regresión del parser ajustado sobre los Excel de 2022-2025.

**Reproducir**, desde la raíz del repo, con MLflow en el 5000:

```bash
python notebooks/16_holdout_2026.py --dw data/processed_real \
    --inventario-dic RUTA/foto_2025-12-31.xlsx --inventario-sep RUTA/foto_2026-09-30.xlsx \
    --parser RUTA/parse_ventas_dir.py
```

## 7. Operación al 30-sep-2026 (CA 8)

Con el veredicto, el DW pasa a operar con las ventas de 2026 y la foto de inventario del 30-sep-2026. El modelo no cambia: el servicio
sigue usando el paquete congelado, ahora con features al 30-sep-2026.

**Qué cambia en el ETL.** Dos variables de entorno nuevas en `etl_real/config.py`, con los valores de antes por defecto:

- `INVENTARIO_FECHA`: la fecha de la foto de `INVENTARIO_XLSX`, hasta ahora fija en 2025-12-31.
- `ETL_SALIDA_DIR`: la carpeta de salida, que también lee `cargar_postgres.py`. Así se arma el DW de la operación sin pisar el que respalda
  el holdout.

**Resultado de la carga local (17-nov-2026):**

| Tabla | Antes (al 31-dic-2025) | Después (al 30-sep-2026) |
|---|---|---|
| `dw.fact_ventas` | 2.056.210 | 2.662.774 |
| `dw.dim_producto` | 4.449 | 4.619 (entran 166 productos de la foto de sep-2026 y salen 126 que ya no están) |
| `dw.fact_inventario` | foto al 2025-12-31 | 11.216 filas, foto al 2026-09-30 |

- La carga terminó con todas las tablas en `OK` frente a sus CSV, en una sola transacción. `database/test-dw-real.SQL` no da ningún
  `NO CUMPLE`.
- Los usuarios de `app.*` se conservan.
- El ML Service reporta `fecha_inventario: 2026-09-30`, y un pronóstico sale con `fecha_features: 2026-09-30` y
  `modelo_entrenado_en: 2026-09-25`. Las huellas de `models/` coinciden con `SHA256SUMS`.
- De los 166 productos nuevos del catálogo, 153 tienen categoría de la revisión manual, 4 la toman de una regla y 9 quedan en «Abarrotes»
  por defecto. Esos 9 los categoriza el negocio, como pide la compuerta del ETL del preregistro.

**Cómo se hizo:**

1. Respaldo de la base local: `pg_dump -Fc`, fuera del repositorio.
2. ETL con `INVENTARIO_XLSX=<foto 2026-09-30>`, `INVENTARIO_FECHA=2026-09-30` y `ETL_SALIDA_DIR=data/processed_real/operacion_2026-09-30`.
   `validar_inventario.py` reescribe `etl_real/productos_excluidos.csv`; esa versión se guarda en la carpeta de salida y el archivo
   versionado se restaura con `git checkout`.
3. `cargar_postgres.py` con la misma `ETL_SALIDA_DIR`.
4. Reinicio de `ml-service`, `api` y `nlp-agent`. Sus cachés dependen de la fecha de la foto o vencen solas; el reinicio las vacía de una
   vez.

**Reversa:** `pg_restore --clean` del respaldo, o volver a correr el ETL sin las variables y `cargar_postgres.py`.

**Staging:** pendiente. Se recarga como indica `docs/INV-34-guia-staging.md` §15, con un volcado de esta base local.

**Efecto en el agente.** Vera ya cita la fecha de la foto (`fecha_dato`), así que no cambia. En cambio, el conjunto de evaluación del
agente (`nlp_agent/evaluacion/construir_v1.py`) califica contra hechos reales al 31-dic-2025. Contra un DW al 30-sep-2026 esos hechos ya no
cuadran: hay que reconstruirlos o evaluar INV-40 antes de recargar staging.

## 8. Exploración preregistrada de features y algoritmos (H10 a H12)

Tras el veredicto, el usuario pidió exprimir los datos 2022 a sep-2026 con features nuevas y otro algoritmo para la rama intermitente (17-nov).
El protocolo se fijó antes de entrenar ningún candidato: `notebooks/preregistro_exploracion_2026.json`, commit `b8f35a7` y run
`preregistro_exploracion_v1` del experimento `EDA-fix-nivel1-17-exploracion-2026`. El código está en `notebooks/17_exploracion_2026.py` y
en `notebooks/exploracion_2026.py`, con pruebas sintéticas (P11).

**Datos.** La rejilla tiene 106 orígenes de 2022 a 2026 sobre los pares D1: 535.222 filas, 97,9 % de la rama intermitente. Se descartaron
2 orígenes de 2022-2023 porque su ventana salta un hueco de datos, como en 07. Las filas de 2026 son idénticas a las del holdout
(diferencia máxima 6e-14).

**Búsqueda** (folds F1 jul-dic 2025, F2 ene-feb 2026 y F3 mar a 3-may 2026, con purge; 21 orígenes y 139.441 filas; run `busqueda`):

| Candidato | Qué agrega | Costo frente a C0 | WAPE frente a C0 | Cobertura |
|---|---|---|---|---|
| C0 | Receta vigente reentrenada | referencia | referencia | 0,892 |
| C1 | Calendario y estacionalidad | +3,1 % [+2,3; +4,1] | +1,5 % [+1,0; +1,9] | 0,899 |
| C2 | Croston-SBA, TSB y otras de demanda intermitente | +0,0 % [−0,8; +0,8] | −0,1 % [−0,4; +0,2] | 0,892 |
| C3 | C1 + C2 | +3,6 % [+2,5; +4,6] | +1,3 % [+0,8; +1,7] | 0,892 |
| C4 | CatBoost con las features de C3 | +4,1 % [+2,7; +5,8] | +1,2 % [+0,6; +1,7] | 0,891 |
| C5 | TSB con razón por estrato, sin ML | −23,5 % [−27,2; −20,4] | −18,5 % | 0,899 |

- Por la regla preregistrada se eligió **C4**: el de menor costo entre los que mejoran a C0 con IC95 > 0, sin empeorar el WAPE y con
  la cobertura a ±0,05.
- El método clásico sin ML pierde por mucho: el ML sí aporta en la cola intermitente.
- El umbral de 200 filas de calibración por estrato no influyó: la cabeza tuvo entre 2.349 y 2.952 filas de calibración en cada fold.

**Confirmación** (una sola vez; 9 orígenes del 18-may al 15-sep-2026, 63.762 filas; C4 entrenado con las ventanas que terminan hasta el
18-may; run `confirmacion`):

| Comparación | Costo | WAPE del q50 | Cobertura (rama / cabeza / medio / cola) |
|---|---|---|---|
| **C4 frente al paquete congelado (decide)** | −0,7 % [−2,3; +0,8] → **E1 no se cumple** | +0,8 % [+0,1; +1,5] → E2 se cumple | 0,896 / 0,896 / 0,886 / 0,899 → E3 se cumple |
| C0 frente al paquete congelado (sin decisión) | −0,3 % [−1,2; +0,6] | +1,4 % [+0,7; +2,3] | — |
| C4 frente a C0 (sin decisión) | −0,4 % [−2,3; +1,1] | −0,6 % [−1,4; +0,2] | — |

**Veredicto: se mantiene la receta vigente.** Ninguna receta nueva supera al paquete congelado en costo, que es la métrica de negocio,
fuera de la muestra de selección. INV-62 reentrena con la receta vigente y debe superar al paquete con las reglas del holdout antes de
promoverse.

**Por qué la ganancia de la búsqueda no se repitió** (análisis sin decisión). Costo de C4 frente a C0, por mes del origen:

| Periodo | C4 frente a C0 |
|---|---|
| oct-2025 a feb-2026 (búsqueda) | +2,2 % a +8,6 % (dic +7,5 %, ene +8,6 %, feb +6,2 %) |
| mar y abr 2026 (búsqueda) | +0,8 % y +1,4 % |
| may a sep 2026 (confirmación) | +1,4 %, +0,9 %, −1,6 %, −1,0 % y −0,1 % |

- Lo que aportan las features de calendario y estacionalidad se concentra entre noviembre y febrero: novenas, navidad, fin de año y arranque
  de enero.
- La ventana de confirmación (may-sep) no tiene esos periodos, así que no puede confirmarlos ni descartarlos.
- La hipótesis queda para INV-62: las features de calendario podrían mejorar el pronóstico en temporada alta. Probarla exige datos limpios
  de oct-2026 a ene-2027, que hoy no existen.

**Advertencias.**

- Los 9 orígenes de confirmación no eran vírgenes: el holdout ya había mostrado cómo le iba allí al paquete congelado. Ningún candidato se
  eligió con ellos y la confirmación se corrió una sola vez.
- Son 6 candidatos en la búsqueda, sin corrección por comparaciones múltiples.
- CatBoost (1.2.8) se agregó al venv de los notebooks solo para C4; no entra en `ml_service`.

**Trazabilidad.** MLflow local, experimento `EDA-fix-nivel1-17-exploracion-2026`:

- `preregistro_exploracion_v1` (`4e359bdf…`);
- `busqueda` (`9af9cb1d…`);
- `confirmacion` (`06567536…`).

Las filas y las predicciones quedan en `data/processed_real/exploracion_2026/`, fuera de git.
