# INV-63 · Evaluación del motor de pronóstico con el holdout 2026 (R1 a R4) · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-63 «Evaluación del motor de pronóstico con el holdout 2026 (reglas R1 a R4)» · 5 SP · Sprint 7 · límite 18-nov |
| Depende de | Las ventas de 2026 convertidas a `ventas_tidy` (formato E, ver C2) |
| Alimenta a | INV-62 (las reglas para aceptar un modelo nuevo) e INV-34 (la política que sirve `ml_service`) |
| Rama | `feature/INV-63-holdout-2026`, desde `develop` (`48c3178`), en el worktree `~/InventaIO-wt/INV-63` |

Revisión del 17 de noviembre de 2026 contra `develop`, el preregistro (`docs/PREREGISTRO-HOLDOUT-2026.md` y su JSON) y los datos reales de 2026. Las decisiones H1 a H3 y H9 las tomó el usuario ese día (formularios y la revisión de su hoja de ruta de ML de 2026); H4 a H8 son técnicas.

## 1. Historia de Jira

> Como científico de datos, quiero evaluar el motor de pronóstico con las ventas de 2026 aplicando las reglas preregistradas R1 a R4, para confirmar o ajustar la política que se despliega en la nube.

Siete criterios (M) y uno (S): los seis (M) y el (S) de la ficha, más el CA 8 (operar al 30-sep-2026), que viene de ajustar la historia con la fase 0 de la hoja de ruta (H9).

Fuera de alcance:
- reentrenar, incluida la máscara de demanda censurada para entrenar (INV-62);
- variables o algoritmos nuevos, como la calibración conformal deslizante;
- decidir sobre pares nuevos;
- el balance de masas, la merma y el backtest de alertas, porque no hay registro de entradas ni foto de agosto de 2026 (C10).

## 2. Contraste con lo ya construido y con los datos

| # | Hallazgo (17-nov) | Consecuencia |
| --- | --- | --- |
| C1 | Los Excel de 2026 (enero a septiembre) son diarios: entre 246.000 y 305.000 filas por mes y un encabezado por día. Existe otra exportación mensual (~2 MB, sin fechas por día) que no sirve | Se usan los diarios |
| C2 | El reporte de 2026 cambió de estructura: producto → factura (sin cifras) → fila de fecha con las 14 cifras → TOTAL. El parser de ventas2 (md5 `aa86a8ad…`) dejaba sin cantidad las 608.305 facturas y sin producto al 95 % | Ajuste del parser: formato E (H2) |
| C3 | Con el ajuste: 607.606 filas y 699 excluidas por calidad (0,11 %); 0 vacíos y 0 duplicados; 27 discrepancias, todas líneas de encabezado. Va del 2026-01-02 al 2026-09-30. La cantidad diaria de enero de 2026 frente a enero de 2025 es 0,90 / 1,00 / 0,91 por sucursal. Hay 148 productos nuevos (3,1 %) | La compuerta de datos del preregistro se cumple, salvo la regresión (C4) |
| C4 | El parser ajustado debe reproducir byte a byte el `ventas_tidy.csv` de 2022-2025 (sha256 `c8363ca6…`). Los 21 Excel históricos están en otra máquina | Regresión pendiente (`~/ventas2/REGRESION-para-segovia.md`) |
| C5 | Hay tres inventarios: 21-ago-2025 (4.399 productos), 31-dic-2025 (4.577, el que usa el ETL) y 30-sep-2026 (4.648). **El de agosto no se usa** (decisión del usuario, 17-nov). Están en dic-2025 y en sep-2026 4.451 productos | Universo D1 (H1) |
| C6 | El universo preregistrado tiene 11.135 pares con estrato. Con la regla de los dos inventarios quedan 10.882 (97,7 %) y salen el 1,3 % de las filas de ventas de 2026 (1,0 % de la cantidad) | Desviación D1, registrada antes de evaluar |
| C7 | Ya existen las piezas: el motor (`ml_service/prediccion/motor.py`: `predecir` y `predecir_lote`), las métricas e IC por bootstrap (`notebooks/evaluar_nivel1.py`) y la verificación de huellas y referencia de R2 (`notebooks/registrar_preregistro_2026.py`) | El evaluador las reutiliza, sin reescribir métricas |
| C8 | Los notebooks 01-07 leen y escriben el DW en `<repo>/data/processed_real` (`common_priorizacion.DW`) y `etl_real` escribe en la misma carpeta. El `data/` del worktree está ignorado por git y no es el del stack local | El worktree sirve de directorio paralelo (H4) |
| C9 | Los días hábiles son los días con alguna venta en el negocio (`common_priorizacion`, sin los «huecos globales»). Del 2026-01-02 al 2026-09-30 hay 271, así que caben 18 orígenes de 15 días hábiles con la ventana completa | Por encima del mínimo de 8: habrá veredicto, no indicio |
| C10 | El inventario «ago 21» es del **21-ago-2025**, no de 2026: de los 132 productos vendidos por primera vez en 2026 antes del 21 de agosto, 115 están en el inventario de sep-2026 y solo 5 en ese | No hay foto de agosto de 2026, ni registro de entradas (compras recibidas o traslados): solo las fotos de dic-2025 y sep-2026 |
| C11 | Con dos fotos y sin entradas: stock ≤ 0 en 1.159 pares (dic-2025) y 1.018 (sep-2026). 149 pares están en negativo en las dos fotos (error persistente del catálogo), 79 solo en dic y 165 solo en sep | Análisis secundarios del holdout (paso 4). No se puede reconstruir cuándo se agotó un par ni la merma |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| H1 | **Universo principal (desviación D1):** pares del paquete congelado cuyo producto está en los inventarios de dic-2025 y de sep-2026. Las ventas de productos fuera de ellos no entran. El veredicto sale de este universo y el preregistrado (v1) se reporta como sensibilidad, sin decisión. El inventario de ago-2025 no se usa | Usuario, 17-nov |
| H2 | **Formato E:** las facturas de 2026 quedan con `formato_detectado = E_transaccional_por_producto`, y la clave de duplicados las trata como A. Los formatos A-D no cambian | Usuario, 17-nov |
| H3 | **Features con el código de 07:** se re-ejecutan los notebooks 01-07 con la historia 2022-2026, sin cambiar su lógica | Usuario, 17-nov |
| H4 | El ETL y los notebooks corren en el worktree de INV-63, con `data/raw_real` propio: `ventas_tidy` 2022-2025 + 2026 y los mismos festivos, terminales e inventario de dic-2025. El DW del stack local no se toca hasta el veredicto | Técnica (C8) |
| H5 | El inventario del ETL sigue siendo el de dic-2025 y los estratos son los del paquete: nada de 2022-2025 cambia. El inventario de sep-2026 solo define el universo D1 hasta el veredicto; después se carga en el DW (H9) | Técnica |
| H6 | La desviación D1 se escribe en `desviaciones` del JSON del preregistro, con fecha y motivo, en un commit anterior a cualquier corrida de la evaluación | Técnica (preregistro, «Desviaciones») |
| H7 | El evaluador se separa en funciones puras (`notebooks/holdout_2026.py`: orígenes, universo, reglas y veredicto) y un orquestador (`notebooks/16_holdout_2026.py`: compuertas, predicción, métricas y MLflow) | Técnica |
| H8 | Si 07 solo materializa su rejilla de entrenamiento, se le agrega un parámetro para la rejilla de 2026 (primer día hábil de 2026 y cada 15), sin tocar el cálculo de las features | Técnica |
| H9 | **Operar «al 30-sep-2026» (de la hoja de ruta, fase 0):** con el veredicto, el DW del stack local y el de staging se recargan con las ventas de 2026 y el inventario de sep-2026. El servicio predice desde esa fecha con la política decidida, y Vera ya cita la fecha de la foto (`fecha_dato`), así que no hay que tocar el agente | Usuario, 17-nov (ajustar historias existentes) |

## 4. Flujo del evaluador

1. **Compuerta de datos (CA 1 y 6):**
   - se arma `data/raw_real/ventas_tidy.csv` del worktree con 2022-2025 + 2026;
   - corren `etl_real` y los notebooks 01-07;
   - se comprueba que las filas de la matriz con origen ≤ 2025-12-12 sean idénticas a las congeladas (hash `8f2d656df51a`);
   - el registro de filas leídas, cargadas y excluidas por motivo queda como artefacto, sin datos del negocio en el repositorio.
2. **Huellas (DoD 3):** `sha256sum -c models/SHA256SUMS` y los SHA-256 del JSON del preregistro.
3. **Orígenes (CA 2):** se toma la rejilla mecánica. Con menos de 8 orígenes, el resultado se reporta como indicio y no activa acciones.
4. **Universo (H1):** principal D1 y v1 como sensibilidad. Aparte, sin decisión: los pares nuevos y los orígenes de diciembre de 2025 (CA 7), el error de los pares con stock ≤ 0 al 31-dic-2025 (posible demanda censurada al empezar) y la clasificación del stock negativo, persistente o pasajero (C11).
5. **Predicción:** `predecir_lote` sobre las filas del holdout, comprobado contra `predecir` en ≥ 1.000 filas (|dif| < 1e-9).
6. **Reglas (CA 3):** R1 a R4 tal como están en el JSON (WAPE, costo Cu/Co, cobertura e IC95 por bootstrap de productos, B=2000, semilla 0), y el veredicto global.
7. **Registro (DoD 4):** un run en MLflow, en el experimento del preregistro (`EDA-fix-nivel1-16-holdout-2026`, como pide su compromiso), con:
   - las reglas, los intervalos y el veredicto;
   - los análisis secundarios del preregistro;
   - las huellas y la desviación D1 como etiqueta.
8. **Decisión (CA 4 y 5):** documento con problema, alternativas, decisión, justificación e impacto. Si alguna regla falla, su acción se aplica en `ml_service` (por ejemplo, reestimar offsets o razones, R3) con sus pruebas, y se actualizan la documentación y «Modelos y decisiones técnicas».
9. **Operar al 30-sep-2026 (H9, DoD 6):** se recarga el DW local con 2022-2026 y el inventario de sep-2026, y se verifica que el servicio sirva la política decidida con «datos al 30-sep-2026». Staging se recarga como indica la guía del staging (§15).

## 5. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) Ventas 2026 por el mismo ETL, sin descartes silenciosos, matriz anterior idéntica | Formato E (H2), regresión del parser (C4) e identidad de la matriz (paso 1) |
| 2 (M) Al menos 8 orígenes | 18 con datos al 30-sep (C9); con menos, indicio |
| 3 (M) R1 a R4 sin cambios, en MLflow | Pasos 6 y 7; la única desviación es el universo (D1), registrada antes |
| 4 (M) Decisión documentada | Paso 8 |
| 5 (M) Decisión reflejada en `ml_service`, docs y Confluence | Pasos 8 y 9, con formulario antes de tocar Confluence |
| 6 (M) Excel y CSV de 2026 fuera del repositorio, con registro de la carga | Datos en `~/ventas2/` y en el `data/` del worktree (ignorado). El registro de la carga es un artefacto de MLflow |
| 7 (S) Pares nuevos y orígenes de diciembre aparte | Paso 4, junto con los análisis de stock con las dos fotos (C11) |
| 8 (M) Operación al 30-sep-2026: DW local y staging con 2026 y el inventario de sep-2026; el servicio sirve la política decidida | Paso 9 (H9) |

## 6. Pruebas

| # | Caso | Dónde |
| --- | --- | --- |
| P1 | La rejilla de orígenes empieza en el primer día hábil de 2026, avanza cada 15 y se detiene cuando la ventana no está completa | `notebooks/tests/test_holdout_2026.py`, con un calendario sintético |
| P2 | Con 7 orígenes el resultado es «indicio» y no hay acciones; con 8, veredicto | Ídem |
| P3 | R1: IC bajo > 0 da confirmada; IC que cruza 0, no confirmada | Ídem, con datos sintéticos |
| P4 | R2: IC > 0 se mantiene; IC que cruza 0 se mantiene y queda «no confirmada»; IC alto < 0 cambia a `baseline_cuantil` | Ídem |
| P5 | R3: estratos con < 200 filas dan «insuficiente»; una desviación > 0,05 dispara la reestimación | Ídem |
| P6 | R4: cobertura más cercana en ≥ 2 de 3 estratos y costo no peor; si no, se desactiva | Ídem |
| P7 | Universo D1: solo entran los pares cuyo producto está en los inventarios de dic-2025 y sep-2026 | Ídem |
| P8 | La compuerta de huellas falla si cambia un byte de un modelo | Ídem, con archivos temporales |
| P9 | Formato E: una factura sin cifras seguida de una fila de fecha con cifras toma esas cifras; una fila de fecha sin cifras sigue siendo encabezado | Pruebas del parser, en `~/ventas2` (fuera de git) |

Las pruebas usan solo datos sintéticos. Corren con el pytest del venv y se documentan en `docs/` (el CI no corre `notebooks/`).

## 7. Ruta

1. **Commit 1:** estos requerimientos y la desviación D1 en el JSON del preregistro, antes de evaluar (H6).
2. Las funciones puras y sus pruebas (P1 a P8).
3. La compuerta de datos en el worktree: ETL, notebooks 01-07 e identidad de la matriz.
4. El orquestador: predicción, reglas, MLflow y los análisis secundarios.
5. La decisión y, si aplica, la acción en `ml_service`, con sus pruebas (cobertura ≥ 90 %).
6. La recarga del DW local y de staging con 2026 y el inventario de sep-2026 (H9).
7. El PR a `develop`. Después, con formulario: «Modelos y decisiones técnicas» en Confluence y Jira.

## 8. Riesgos

- **La regresión del parser (C4)** depende de la otra máquina. Si no se puede correr antes del cierre, se documenta como pendiente: el ajuste no toca los formatos A-D (P9).
- **La identidad de la matriz puede fallar** si el ETL cambia algo de 2022-2025 al ver productos nuevos (por ejemplo, la clasificación). Si pasa, se documenta antes de seguir, como pide el preregistro.
- **Disco:** `ventas_tidy` completo pesa ~735 MB y los notebooks generan ~1 GB en el worktree. En C: hay ~82 GB libres.
- **Tiempo:** el límite es el 18-nov y el sprint cierra el 20-nov. El punto de control es el jue 19 al mediodía.
