# INV-63 · Evaluación del motor de pronóstico con las ventas de 2026 · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-63 «Evaluación del motor de pronóstico con el holdout 2026 (reglas R1 a R4)» · 5 puntos de historia · Sprint 7 · fecha límite 18-nov |
| Depende de | Las ventas de 2026 convertidas al formato tabular del ETL (`ventas_tidy`), con el ajuste del parser para el reporte nuevo |
| Alimenta a | INV-62 (el reentrenamiento, que usará estas mismas reglas para aceptar un modelo nuevo) e INV-34 (la política que sirve el servicio de predicción en la nube) |
| Rama | `feature/INV-63-holdout-2026`, desde `develop` (`48c3178`), en el worktree `~/InventaIO-wt/INV-63` |

Revisión del 17 de noviembre de 2026 contra `develop`, el preregistro (`docs/PREREGISTRO-HOLDOUT-2026.md` y su JSON) y los datos reales de
2026. Las decisiones del usuario salen de los formularios de ese día y de la revisión de su hoja de ruta de ML de 2026; las demás son
técnicas.

## Términos que se usan en este documento

| Término | Qué significa aquí |
| --- | --- |
| Holdout | Datos que el motor no vio al diseñarse: las ventas de enero a septiembre de 2026 |
| Preregistro | Documento del 25-sep-2026, escrito antes de ver datos de 2026, que congela el modelo y fija las reglas de evaluación y la acción de cada una |
| Paquete congelado | Los tres modelos en producción (`models/`), verificados por su huella SHA-256 |
| Origen | Fecha desde la que se pronostica; la ventana objetivo son los 15 días hábiles siguientes |
| Día hábil | Día con alguna venta en el negocio |
| Estrato | Cabeza, medio o cola, según el volumen acumulado del par (producto, sucursal) al 31-dic-2025 |
| Cuantil de negocio | La cantidad que usa la reposición: cubre la demanda con probabilidad 0,893 en los no perecederos y 0,167 en los perecederos |
| Cobertura | Fracción de filas con la demanda real menor o igual al cuantil de negocio |
| WAPE | Error porcentual absoluto ponderado de la mediana: suma de los errores absolutos dividida entre la suma de la demanda |
| Costo | Costo de faltante más costo de sobrante: 0,25 por unidad faltante y 0,03 por unidad sobrante en los no perecederos |
| Intervalo de confianza del 95 % | Rango de la mejora calculado por bootstrap de productos (se remuestrean productos 2.000 veces, semilla 0). Si queda entero por encima de 0, la mejora es distinguible del ruido |
| Purge | Al entrenar, se descartan las filas cuya ventana objetivo se mete en el periodo evaluado, para que el modelo no vea el futuro |

## 1. Historia de Jira

> Como científico de datos, quiero evaluar el motor de pronóstico con las ventas de 2026 aplicando las cuatro reglas preregistradas, para
> confirmar o ajustar la política que se despliega en la nube.

**Las cuatro reglas del preregistro** (sus identificadores, R1 a R4, son los del JSON y de MLflow):

| Regla | Qué mide | Se cumple si | Si no se cumple |
| --- | --- | --- | --- |
| Precisión (R1) | Error de la mediana de la rama intermitente frente a la media móvil | La mejora del WAPE tiene un intervalo de confianza del 95 % por encima de 0 | No se confirma; se reevalúa al reentrenar (INV-62) |
| Costo (R2) | Costo del cuantil de negocio de la rama intermitente frente a la referencia simple congelada (`baseline_cuantil`) | La mejora del costo tiene un intervalo por encima de 0 | Si el intervalo cruza 0, se mantiene sin confirmar; si queda entero por debajo, la rama pasa a la referencia simple |
| Calibración (R3) | Cobertura de las tres ramas | Queda a menos de 0,05 de su objetivo en cada rama y en cada estrato con al menos 200 filas | Se reestiman los ajustes de calibración con 2026, sin tocar el modelo |
| Calibración por estrato (R4) | El ajuste por estrato de la rama intermitente frente a la misma predicción sin ajuste | La cobertura queda más cerca de 0,893 en al menos 2 de los 3 estratos y el costo no empeora | Se desactiva el ajuste por estrato |

**Criterios de aceptación de la ficha:** siete obligatorios y uno deseable. Los seis obligatorios y el deseable vienen de la ficha original;
el octavo (operar con los datos al 30-sep-2026) se agregó al ajustar la historia con la fase 0 de la hoja de ruta. El 17-nov se propuso un
noveno, deseable, para la exploración de features y algoritmos (sección 8).

**Fuera de alcance:**
- reentrenar, incluida la máscara de demanda censurada para entrenar (va en INV-62);
- variables o algoritmos nuevos en producción (la exploración de la sección 8 solo recomienda una receta para INV-62);
- decidir sobre pares nuevos;
- el balance de masas, la merma y el backtest de alertas: no hay registro de entradas (compras recibidas ni traslados) ni foto de
  inventario de agosto de 2026.

## 2. Hallazgos al contrastar con lo ya construido y con los datos

| Hallazgo (17-nov) | Consecuencia |
| --- | --- |
| **Excel diarios.** Los Excel de 2026 (enero a septiembre) son diarios: entre 246.000 y 305.000 filas por mes y un encabezado por día. Existe otra exportación mensual (unos 2 MB, sin fechas por día) que no sirve | Se usan los diarios |
| **Reporte con otra estructura.** El reporte de 2026 cambió: producto, luego la factura (sin cifras), luego una fila de fecha con las 14 cifras y al final el total. El parser de ventas2 (md5 `aa86a8ad…`) dejaba sin cantidad las 608.305 facturas y sin producto al 95 % | El parser se ajusta con un formato nuevo, el formato E (decisión «formato E» de la sección 3) |
| **Conversión validada.** Con el ajuste: 607.606 filas y 699 excluidas por calidad (0,11 %); 0 campos vacíos y 0 duplicados; 27 discrepancias, todas líneas de encabezado. Va del 2026-01-02 al 2026-09-30. La cantidad diaria de enero de 2026 frente a enero de 2025 es 0,90 / 1,00 / 0,91 por sucursal. Hay 148 productos nuevos (3,1 %) | La compuerta de datos del preregistro se cumple, salvo la prueba de regresión del parser (siguiente fila) |
| **Regresión del parser pendiente.** El parser ajustado debe reproducir byte a byte el `ventas_tidy.csv` de 2022-2025 (sha256 `c8363ca6…`). Los 21 Excel históricos están en otra máquina (servidor segovia) | Pendiente; instrucciones en `~/ventas2/REGRESION-para-segovia.md` |
| **Tres fotos de inventario.** 21-ago-2025 (4.399 productos), 31-dic-2025 (4.577, la que usa el ETL) y 30-sep-2026 (4.648). **La de agosto no se usa** (decisión del usuario, 17-nov). En dic-2025 y en sep-2026 están 4.451 productos | Universo principal de la evaluación (decisión «universo» de la sección 3) |
| **Efecto de la regla de inventario.** El universo preregistrado tiene 11.135 pares con estrato. Con la regla de las dos fotos quedan 10.882 (97,7 %) y salen el 1,3 % de las filas de ventas de 2026 (1,0 % de la cantidad) | Se registra como desviación del preregistro antes de evaluar (desviación D1) |
| **Piezas reutilizables.** Ya existen el motor (`ml_service/prediccion/motor.py`: `predecir` y `predecir_lote`), las métricas e intervalos por bootstrap (`notebooks/evaluar_nivel1.py`) y la verificación de huellas y de la referencia de la regla de costo (`notebooks/registrar_preregistro_2026.py`) | El evaluador las reutiliza, sin reescribir métricas |
| **Directorio paralelo.** Los notebooks 01-07 y `etl_real` leen y escriben el DW en `<repo>/data/processed_real`. El `data/` del worktree está ignorado por git y no es el del stack local | El worktree sirve de DW paralelo (decisión «ETL en el worktree») |
| **Orígenes disponibles.** Del 2026-01-02 al 2026-09-30 hay 271 días hábiles, así que caben 18 orígenes con la ventana de 15 días completa | Por encima del mínimo de 8: hay veredicto, no indicio |
| **La foto «ago 21» es de 2025.** De los 132 productos vendidos por primera vez en 2026 antes del 21 de agosto, 115 están en la foto de sep-2026 y solo 5 en esa | No hay foto de agosto de 2026 ni registro de entradas: solo las fotos de dic-2025 y sep-2026 |
| **Señales de stock con dos fotos.** Contando todas las ubicaciones y agregando por producto y ubicación: 1.158 pares con stock ≤ 0 al 31-dic-2025; 149 en negativo en las dos fotos (error persistente del catálogo), 86 solo en dic y 217 solo en sep. La versión preliminar de esta tabla decía 1.159 / 79 / 165, con otra agregación | Análisis secundarios de la evaluación. No se puede reconstruir cuándo se agotó un par ni la merma |

## 3. Decisiones

| Decisión | Qué se decidió | Origen |
| --- | --- | --- |
| **Universo** (desviación D1 del preregistro) | Entran los pares del paquete congelado cuyo producto está en las fotos de dic-2025 y de sep-2026. Las ventas de productos fuera de ellas no entran. El veredicto sale de este universo; el preregistrado se reporta como sensibilidad, sin decisión. La foto de ago-2025 no se usa | Usuario, 17-nov |
| **Formato E** | Las facturas de 2026 quedan con `formato_detectado = E_transaccional_por_producto`, y la clave de duplicados las trata como el formato A. Los formatos A a D no cambian | Usuario, 17-nov |
| **Features con el código del servicio** (desviación D2) | Las features se calculan con `ml_service/prediccion/features.py` y los parámetros congelados del paquete (`models/nivel1_parametros_features.json`), sobre la venta diaria neta del DW 2022-2026. Las features estáticas, a la fecha de cada origen, como en el servicio. Reemplaza la re-ejecución de los notebooks 01-07: el 07 lee efectos de calendario y priorización que el 02 a 04 vuelven a estimar con toda la historia, y el preregistro los congela | Usuario, 17-nov (segundo formulario) |
| **ETL en el worktree** | El ETL corre en el worktree de INV-63, con su propio `data/raw_real`: las ventas 2022-2025 más 2026 y los mismos festivos, terminales y foto de dic-2025. El DW del stack local no se toca hasta el veredicto | Técnica |
| **Nada de 2022-2025 cambia** | El inventario del ETL sigue siendo el de dic-2025 y los estratos son los del paquete. La foto de sep-2026 solo define el universo hasta el veredicto; después se carga en el DW (decisión «operar al 30-sep») | Técnica |
| **Desviaciones antes de evaluar** | Cada desviación se escribe en el JSON del preregistro, con fecha y motivo, en un commit anterior a cualquier corrida de la evaluación | Técnica (lo pide el preregistro) |
| **Funciones puras y orquestador** | Las reglas y el veredicto van en funciones puras (`notebooks/holdout_2026.py`), probadas con datos sintéticos; los datos, la predicción, las métricas y MLflow, en un orquestador (`notebooks/16_holdout_2026.py`) | Técnica |
| **Rejilla mecánica** | Los orígenes de 2026 los arma `holdout_2026.origenes_holdout` sobre los días hábiles del DW, sin tocar el notebook 07 | Técnica |
| **Operar al 30-sep-2026** (fase 0 de la hoja de ruta) | Con el veredicto, el DW del stack local y el de staging se recargan con las ventas de 2026 y la foto de sep-2026. El servicio predice desde esa fecha con la política decidida. Vera ya cita la fecha de la foto (`fecha_dato`), así que el agente no cambia | Usuario, 17-nov (ajustar las historias existentes en vez de crear nuevas) |
| **Exploración dentro de INV-63** | Después del veredicto, con los datos 2022 a sep-2026, se prueban features nuevas y un algoritmo distinto para la rama intermitente. El resultado es la receta para el reentrenamiento de INV-62; el veredicto de la evaluación no cambia | Usuario, 17-nov |
| **Corte preregistrado para la exploración** | Se buscan candidatos con los orígenes hasta el 3-may-2026 y se confirma una sola vez con los 9 siguientes (18-may a 15-sep), frente al paquete congelado. El protocolo (`notebooks/preregistro_exploracion_2026.json`) se registra en un commit y en MLflow antes de entrenar cualquier candidato | Usuario, 17-nov |
| **Exploración antes de INV-40** | La exploración va antes de la evaluación del agente en staging | Usuario, 17-nov |

## 4. Flujo de la evaluación

1. **Compuerta de datos** (criterios 1 y 6):
   - se arma el `ventas_tidy.csv` del worktree con 2022-2025 más 2026 y corre `etl_real`;
   - la serie diaria neta 2022-2025 debe quedar idéntica a la del DW vigente (huella `82d3a820b3d9`: cumplido el 17-nov);
   - la paridad de `features.py` con la matriz de entrenamiento congelada se repite cuando esa matriz esté disponible (servidor segovia);
   - el registro de filas leídas, cargadas y excluidas por motivo queda como artefacto, sin datos del negocio en el repositorio.
2. **Huellas del paquete** (punto 3 de la definición de terminado): `sha256sum -c models/SHA256SUMS` y los SHA-256 del JSON del
   preregistro.
3. **Orígenes** (criterio 2): la rejilla mecánica. Con menos de 8 orígenes, el resultado es un indicio y no activa acciones.
4. **Universo:** el principal (productos en las dos fotos) y el preregistrado como sensibilidad. Aparte y sin decisión (criterio 7):
   - los pares nuevos y los orígenes de diciembre de 2025;
   - el error de los pares con stock ≤ 0 al 31-dic-2025 (posible demanda censurada al empezar);
   - el stock negativo persistente frente al pasajero.
5. **Predicción:** `predecir_lote` sobre las filas de 2026, comprobado contra `predecir` fila a fila en al menos 1.000 filas (diferencia
   menor que 1e-9).
6. **Reglas** (criterio 3): las cuatro reglas tal como están en el JSON, y el veredicto global.
7. **Registro en MLflow** (punto 4 de la definición de terminado): un run en el experimento del preregistro
   (`EDA-fix-nivel1-16-holdout-2026`), con:
   - las reglas, los intervalos y el veredicto;
   - los análisis secundarios;
   - las huellas y las desviaciones como etiquetas.
8. **Decisión** (criterios 4 y 5): documento con problema, alternativas, decisión, justificación e impacto. Si alguna regla falla, su
   acción se aplica en `ml_service`, con sus pruebas, y se actualizan la documentación y la página «Modelos y decisiones técnicas».
9. **Operar al 30-sep-2026** (criterio 8 y punto 6 de la definición de terminado): se recarga el DW local con 2022-2026 y la foto de
   sep-2026, y se verifica que el servicio sirva la política decidida con «datos al 30-sep-2026». Staging se recarga como indica la guía
   del staging, sección 15.

## 5. Criterios de aceptación

| Criterio de la ficha | Cómo se cumple |
| --- | --- |
| 1, obligatorio: ventas de 2026 por el mismo ETL, sin descartes silenciosos y con la matriz anterior idéntica | Formato E, regresión del parser e identidad de la serie diaria 2022-2025 (paso 1); la paridad con la matriz congelada, cuando esté disponible |
| 2, obligatorio: al menos 8 orígenes | 18 con datos al 30-sep; con menos, indicio |
| 3, obligatorio: las cuatro reglas sin cambios, registradas en MLflow | Pasos 6 y 7; las desviaciones (universo y cálculo de features) se registraron antes de evaluar |
| 4, obligatorio: decisión documentada | Paso 8 |
| 5, obligatorio: decisión reflejada en `ml_service`, la documentación y Confluence | Pasos 8 y 9, con formulario antes de tocar Confluence |
| 6, obligatorio: Excel y CSV de 2026 fuera del repositorio, con registro de la carga | Datos en `~/ventas2/` y en el `data/` del worktree (ignorado por git). El registro de la carga es un artefacto de MLflow |
| 7, deseable: pares nuevos y orígenes de diciembre, aparte | Paso 4, junto con las señales de stock de las dos fotos |
| 8, obligatorio: operación al 30-sep-2026, con el DW local y el de staging al día y el servicio con la política decidida | Paso 9 |
| 9, deseable (propuesto el 17-nov): la exploración se corre con el protocolo preregistrado y su resultado queda en MLflow y en docs/, cumpla o no | Sección 8 |

## 6. Pruebas

Todas usan datos sintéticos, corren con el pytest del venv y se documentan en `docs/`; el CI no corre `notebooks/`. En el código, cada
bloque de pruebas lleva el mismo nombre que en esta tabla.

| Qué se prueba | Dónde |
| --- | --- |
| **Rejilla de orígenes:** empieza en el primer día hábil de 2026, avanza cada 15 y se detiene cuando la ventana no está completa | `notebooks/tests/test_holdout_2026.py`, con un calendario sintético |
| **Indicio o veredicto:** con 7 orígenes el resultado es un indicio, sin acciones; con 8, veredicto | Ídem |
| **Regla de precisión:** con el intervalo entero por encima de 0, confirmada; si cruza 0, no confirmada | Ídem |
| **Regla de costo:** los tres casos (intervalo por encima de 0, que cruza 0 y entero por debajo, que cambia la rama a la referencia simple) | Ídem |
| **Regla de calibración:** un estrato con menos de 200 filas no decide; un desvío mayor que 0,05 dispara la reestimación | Ídem |
| **Regla de calibración por estrato:** se cumple con 2 de 3 estratos más cerca y costo no peor; si no, se desactiva | Ídem |
| **Universo:** solo entran los pares cuyo producto está en las dos fotos | Ídem |
| **Huellas:** la compuerta falla si cambia un byte de un modelo | Ídem, con archivos temporales |
| **Formato E del parser:** una factura sin cifras seguida de una fila de fecha con cifras toma esas cifras; una fila de fecha sin cifras sigue siendo encabezado | Pruebas del parser, en `~/ventas2` (fuera de git) |
| **Evaluación de un universo:** arma las cuatro reglas con sus entradas y, con menos de 8 orígenes, no activa acciones | `notebooks/tests/test_holdout_2026.py` |
| **Features de la exploración:** Croston-SBA, TSB, media exponencial, venta del año anterior y marcas de calendario, contra resultados calculados a mano; la partición con purge; las reglas de selección y de confirmación | `notebooks/tests/test_exploracion_2026.py` |

## 7. Ruta

1. Estos requerimientos y la desviación del universo en el JSON del preregistro, en un commit anterior a evaluar.
2. Las funciones puras y sus pruebas.
3. La compuerta de datos en el worktree: ETL e identidad de la serie diaria 2022-2025.
4. El orquestador: predicción, reglas, MLflow y los análisis secundarios.
5. La decisión y, si aplica, la acción en `ml_service`, con sus pruebas (cobertura de al menos 90 %).
6. La recarga del DW local y de staging con 2026 y la foto de sep-2026.
7. La exploración preregistrada (sección 8).
8. El PR a `develop`. Después, con formulario: la página «Modelos y decisiones técnicas» en Confluence y la ficha de Jira.

## 8. Exploración preregistrada de features y algoritmos

Protocolo completo en `notebooks/preregistro_exploracion_2026.json`. Resumen:

| Aspecto | Qué se fijó antes de correr |
| --- | --- |
| Universo | Los pares con el producto en las dos fotos. Solo la rama intermitente tiene candidatos: las suaves (81 pares) no alcanzan para elegir modelos |
| Rejilla | Orígenes cada 15 días hábiles anclados en el 2026-01-02, desde el inicio de la historia hasta el 2026-09-15 |
| Búsqueda | Tres periodos de prueba, con purge: jul-dic 2025, ene-feb 2026 y mar a 3-may 2026 |
| Confirmación | Los 9 orígenes del 18-may al 15-sep-2026, con el modelo entrenado una sola vez con las ventanas que terminan hasta el 18-may |
| Candidatos | Seis, con estos identificadores en MLflow: receta vigente reentrenada (C0); con features de calendario y estacionalidad (C1); con features de demanda intermitente, como Croston-SBA y TSB (C2); con las dos familias (C3); CatBoost con las dos familias (C4); y TSB clásico con razón por estrato, sin ML (C5) |
| Regla de selección | Gana el de menor costo entre los que mejoran el costo frente a la receta vigente reentrenada con intervalo por encima de 0, no empeoran el WAPE y tienen la cobertura a menos de 0,05 de 0,893. Si ninguno cumple, gana la receta vigente reentrenada |
| Criterios de la confirmación | Costo frente al paquete congelado con intervalo por encima de 0 (E1); WAPE no peor (E2); cobertura a menos de 0,05 de 0,893 en la rama y en los estratos con al menos 200 filas (E3) |
| Veredicto | Si se cumplen los tres criterios, la receta se recomienda para INV-62. Si no, INV-62 reentrena con la receta vigente y debe superar al paquete con las reglas de la evaluación |

Los 9 orígenes de la confirmación no son vírgenes: la evaluación ya mostró cómo le fue allí al paquete congelado. Ningún candidato se eligió
con ellos y la advertencia acompaña al resultado.

**Resultado (17-nov):** la búsqueda eligió CatBoost con las dos familias de features, que mejoró el costo un 4,1 % frente a la receta
vigente reentrenada. En la confirmación no supera al paquete congelado en costo: −0,7 %, con un intervalo de [−2,3; +0,8] que cruza 0.
Se mantiene la receta vigente. Detalle en `docs/INV-63-holdout-2026.md`, sección 8.

## 9. Riesgos

- **La regresión del parser** depende de la máquina que tiene los Excel de 2022-2025. Si no se corre antes del cierre, queda documentada
  como pendiente; el ajuste no toca los formatos A a D.
- **La paridad con la matriz congelada** necesita la matriz del servidor segovia, desconectado el 17-nov. La serie diaria 2022-2025 ya se
  comprobó idéntica; la paridad de features se corre cuando esté la matriz.
- **Disco:** el `ventas_tidy` completo pesa unos 735 MB y el DW del worktree unos 250 MB. En C: hay unos 71 GB libres.
- **Tiempo:** la fecha límite es el 18-nov y el sprint cierra el 20-nov. La exploración compite con INV-40, que va después.
- **CatBoost** se instaló en el venv de los notebooks (versión 1.2.8, unos 100 MB) solo para la exploración; no entra en `ml_service`.
