# INV-62 · Reentrenamiento programado de los modelos de pronóstico · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-62 «Programación automática del reentrenamiento» · Sprint 7 · fecha límite 20-nov |
| Depende de | INV-63: las reglas para aceptar un modelo, el orquestador del holdout, la exploración y el ETL con la fecha de la foto configurable |
| Rama | `feature/INV-62-reentrenamiento`, apilada sobre `feature/INV-63-holdout-2026` (`89d9fa3`), en el worktree `~/InventaIO-wt/INV-62`. Se rebasa sobre `develop` cuando INV-63 se integre |
| En paralelo | INV-40 (agente) la trabaja otra sesión; no comparten archivos |

Revisión del 18 de noviembre de 2026 contra la ficha de Jira, el resultado de INV-63, el análisis externo de Gemini sobre ese resultado y los
datos. Los términos (holdout, origen, estrato, cuantil de negocio, cobertura, WAPE, intervalo de confianza del 95 %, purge) están definidos en
`docs/INV-63-requerimientos.md`. Además, en este documento:

| Término | Qué significa aquí |
| --- | --- |
| Receta | Cómo se entrena el modelo de la rama intermitente: algoritmo, features, filas de entrenamiento y calibración |
| Modelo vigente | El paquete que sirve hoy el servicio de predicción: el congelado del 25-sep-2026 hasta que se promueva otro |
| Candidato | El paquete que produce una corrida del reentrenamiento con la receta y los datos de ese momento |
| Corte | Última fecha de datos con la que se entrena |
| Temporada alta | De noviembre a febrero (novenas, navidad, fin de año y arranque de enero) |

## 1. Historia de Jira

> Como científico de datos, quiero que el reentrenamiento de los modelos de pronóstico se ejecute de forma programada, para mantener las
> predicciones actualizadas sin intervención manual.

**Lo que dice la ficha (10-nov):**

- La tarea corre en el equipo local (WSL) con un temporizador de systemd, porque usa datos del negocio y el repositorio es público.
- Automatizada hasta el candidato, con promoción humana: si el candidato pasa las reglas, queda en una rama con sus huellas y se integra por PR.
- Fuera de alcance: correr en la nube, cambiar algoritmos o variables y cargar los Excel de ventas, que sigue siendo manual.

**Criterios de la ficha:**

1. (obligatorio) El reentrenamiento corre con un temporizador de systemd en WSL, semanal, y no entrena si no hay datos nuevos.
2. (obligatorio) Cada ejecución registra un run en MLflow con sus métricas y la versión de los datos (última fecha y huella).
3. (obligatorio) Un modelo nuevo no reemplaza al vigente si no cumple las reglas.
4. (obligatorio) Si pasa, se regenera `models/SHA256SUMS` en una rama propia y la promoción es por PR.
5. (obligatorio) Falla de forma visible (registro y estado del temporizador) si el reentrenamiento no termina o MLflow no responde.
6. (obligatorio) Proceso documentado, con la reversa al modelo anterior.
7. (deseable) Si el equipo estuvo apagado, la siguiente ejecución recupera la pendiente.

**Lo que se agrega (decisiones del 17 y 18 de noviembre, sin crear historias nuevas):**

- el primer reentrenamiento real, con corte al 30-sep-2026 y el catálogo vivo (los productos de la foto de sep-2026);
- la máscara de demanda censurada en el entrenamiento;
- la replicación de las features de calendario en tres temporadas altas y, si replican, llevarlas al servicio de predicción;
- la simulación de una calibración adaptativa para la cabeza.

Agregar las features de calendario contradice el «fuera de alcance» de la ficha. Se agrega por decisión del usuario del 18-nov y la ficha se
actualiza con formulario.

## 2. Hallazgos al contrastar con lo construido y con los datos

| Hallazgo (18-nov) | Consecuencia |
| --- | --- |
| **Reentrenar no basta.** En la confirmación de INV-63, la receta vigente reentrenada con datos hasta mayo de 2026 no bajó el costo frente al paquete congelado: −0,3 % [−1,2; +0,6], con un WAPE +1,4 % mejor | Con la regla de promoción elegida, es probable que un reentrenamiento sin cambios de receta salga rechazado. Ese es un resultado válido del proceso, no una falla |
| **El calendario no se pudo probar en temporada alta.** CatBoost con features de calendario ganó entre octubre y febrero (diciembre +7,5 %, enero +8,6 %) y no de mayo a septiembre. Además, los mismos meses de julio a septiembre ganaban en 2025 (+0,3 % a +2,8 %) y perdían en 2026 (−0,1 % a −1,6 %): parte de la ganancia de la búsqueda era optimismo por elegir entre seis candidatos | Hace falta replicar en temporadas distintas. Hay tres temporadas altas completas, con 8 orígenes cada una: 2023-24, 2024-25 y 2025-26 |
| **La máscara de demanda censurada toca muy poco.** Con las fotos de dic-2025 y sep-2026: 348 y 403 pares intermitentes con stock ≤ 0. Solo unos 140 en cada foto llevaban 15 días hábiles o más sin vender, lo que enmascara unas 1.350 filas de 524.000 (0,26 %) | Se implementa como protección, sin esperar efecto medible. Corregir la censura de verdad exige inventario diario o el registro de entradas, que no existen |
| **El stock negativo no es censura.** Significa que se vendió más de lo registrado: la venta no estuvo limitada. El análisis externo los confundía | Los pares con stock negativo no se enmascaran |
| **La foto «del 21-ago-2026» es del 21-ago-2025.** Lo verificamos el 17-nov | No se usa (decisión del usuario del 18-nov) |
| **La cabeza pesa mucho y queda corta.** Es el 2,4 % de las filas, pero el 37 % de la demanda y el 27 % del costo, y su cobertura en 2026 fue 0,877 frente a 0,893. Separarla del modelo global ya se probó sin mejora (decisión 6) | La calibración adaptativa se simula sobre la cabeza |
| **Pocos ceros a 15 días.** Solo el 25 % de las ventanas intermitentes tiene demanda cero (cola 33 %, cabeza 1,4 %) | Un modelo en dos etapas ayudaría sobre todo a la cola; no entra en este sprint |
| **El servicio calcula 14 features fijas.** `ml_service/prediccion/features.py` no tiene las de calendario y el servicio no tiene CatBoost | Si el calendario replica, se amplía `features.py` con pruebas de paridad. El algoritmo sigue siendo LightGBM |
| **systemd de usuario funciona en WSL**, pero sin «linger»: el temporizador corre solo con una sesión de WSL abierta | Se documenta; con el disparo pendiente recuperado (criterio 7) se recupera al abrir WSL |
| **El DW que se usa para entrenar** son los CSV del ETL. El de operación al 30-sep-2026 está en el worktree de INV-63 (`data/processed_real/operacion_2026-09-30`) | La carpeta del DW es un parámetro del reentrenamiento |

## 3. Decisiones

| Decisión | Qué se decidió | Origen |
| --- | --- | --- |
| **Dónde corre** | En WSL, con un temporizador de systemd de usuario semanal y con el disparo pendiente recuperado (`Persistent=true`). MLflow es el local del puerto 5000 | Ficha, 10-nov |
| **Promoción con evidencia walk-forward** | En los últimos 12 orígenes con la ventana completa, la receta candidata se entrena en 3 cortes (cada 4 orígenes, con purge) y se compara con el modelo vigente sobre las mismas filas. Pasa si cumple los tres criterios de la exploración: baja el costo con intervalo por encima de 0, no empeora el WAPE (el extremo alto del intervalo es 0 o más) y deja la cobertura a 0,05 o menos de 0,893 en la rama y en cada estrato con al menos 200 filas. Si no pasa, queda registrado como rechazado y el vigente no cambia | Usuario, 18-nov |
| **Promoción humana** | Si pasa, el candidato queda en una rama local `reentrenamiento/AAAAMMDD` con `models/` y `SHA256SUMS` regenerados. El usuario hace el push y abre el PR | Ficha, 10-nov |
| **Receta base** | LightGBM sobre la demanda relativa a la media móvil, con los hiperparámetros vigentes y la calibración por estrato; ramas suaves con la referencia simple y sus razones reestimadas | Vigente (decisión 40) |
| **Máscara de demanda censurada** | Se excluyen del entrenamiento las filas de un par con stock ≤ 0 en una foto que llevaba 15 días hábiles o más sin vender antes de esa foto, cuya ventana objetivo cae entre la última venta y la foto. El stock negativo no se enmascara | Usuario, 18-nov |
| **Features de calendario** | Entran en la receta solo si replican en las tres temporadas altas con la regla de la sección 5, sin dañar el resto del año. Si entran, se amplía `features.py` y su prueba de paridad | Usuario, 18-nov |
| **Calibración adaptativa** | Solo se simula con las predicciones ya guardadas del holdout y se reporta; no se integra | Usuario, 18-nov |
| **Foto de ago-2025** | No se usa | Usuario, 18-nov |
| **Catálogo vivo y estratos** | Entran los pares de las sucursales modeladas cuyo producto está en el catálogo del DW. Los estratos se recalculan al corte, con la misma definición: volumen de los últimos 365 días hábiles, cabeza hasta el 50 % y medio hasta el 80 % | Técnica (plan del 17-nov) |
| **Estado entre corridas** | La versión de los datos de la última corrida (fecha máxima y huella de `fact_ventas.csv`) se lee de MLflow, del experimento `INV-62-reentrenamiento-nivel1` | Técnica |
| **Rama apilada** | INV-62 parte de la rama local de INV-63; los dos PR se abren el viernes | Usuario, 18-nov |

## 4. Flujo de una corrida programada

1. **Compuertas:** MLflow responde (si no, la corrida falla con código distinto de 0 y queda en el estado de systemd); las huellas de
   `models/` coinciden con `SHA256SUMS`.
2. **¿Hay datos nuevos?** Si la fecha máxima y la huella de `fact_ventas.csv` son las de la última corrida terminada, se registra un run
   «sin datos nuevos» y termina con código 0.
3. **Matriz:** la rejilla de orígenes cada 15 días hábiles hasta el corte, con las features de la receta, el objetivo y el fin de cada ventana.
4. **Evaluación walk-forward:** los 3 cortes sobre los últimos 12 orígenes, frente al modelo vigente; los tres criterios.
5. **Si pasa:** entrena el candidato con todos los datos hasta el corte, lo exporta (los tres paquetes, los metadatos y `SHA256SUMS`), lo deja
   en la rama `reentrenamiento/AAAAMMDD` y registra el run como «promovible».
6. **Si no pasa:** registra el run como «rechazado», con las métricas y el motivo.
7. **Registro:** cada run lleva la versión de los datos, la receta, las métricas de los tres criterios por estrato y el estado.

**Reversa:** los modelos van dentro de la imagen, así que volver al anterior es revertir el commit del PR del candidato y desplegar la
versión anterior. En local, `git checkout <commit> -- models/` y reiniciar el servicio de predicción.

## 5. Evaluación de la receta, preregistrada antes de correr

El protocolo va en `notebooks/preregistro_receta_2026.json`, en un commit y en MLflow antes de entrenar nada. Los datos de 2022 a sep-2026
ya se usaron para diseñar y evaluar el motor: esto sirve para elegir la receta, no para confirmarla. La confirmación limpia de la temporada
alta será con las ventas de oct-2026 a ene-2027, cuando lleguen.

**Replicación del calendario:**

- **Comparación:** la receta vigente (14 features) frente a la misma con las features de calendario y estacionalidad (las del candidato C1
  de la exploración), las dos con LightGBM y la máscara de censura.
- **Temporadas altas:** se prueba con los orígenes de noviembre a febrero de 2023-24, de 2024-25 y de 2025-26, entrenando con las ventanas
  que terminan antes de cada temporada (walk-forward con purge).
- **Resto del año:** se prueba con los orígenes de marzo a octubre de 2024 y de 2025, y de marzo a septiembre de 2026, de la misma forma.
- **Regla:** las features de calendario entran si se cumplen las tres condiciones:
  - en cada una de las tres temporadas altas bajan el costo con un intervalo de confianza del 95 % por encima de 0;
  - en el resto del año, juntando los tres años, no empeoran el costo (el extremo alto del intervalo es 0 o más);
  - en todas las pruebas juntas, no empeoran el WAPE y dejan la cobertura a 0,05 o menos de 0,893.

**Máscara de demanda censurada:** entra por decisión del usuario. Se reporta su efecto sobre las filas que no enmascara.

**Calibración adaptativa** (solo se reporta): sobre las predicciones guardadas del holdout de 2026 se comparan el ajuste fijo por estrato
(el vigente) y dos variantes:

- un ajuste recalculado en cada origen con los residuos de los 6 orígenes anteriores;
- el método de Gibbs y Candès, que corrige el nivel del cuantil en cada origen según los aciertos recientes.

Se reporta la cobertura por estrato, con la cabeza primero, y el costo.

## 6. Criterios de aceptación

| Criterio | Cómo se cumple |
| --- | --- |
| 1, temporizador semanal sin datos nuevos | Unidad y temporizador de systemd de usuario; el paso 2 del flujo |
| 2, run en MLflow con la versión de los datos | Paso 7 del flujo, en `INV-62-reentrenamiento-nivel1` |
| 3, no reemplaza al vigente si no cumple las reglas | Paso 4 del flujo, con la regla de promoción de la sección 3 |
| 4, rama propia y PR | Paso 5 del flujo; el usuario hace el push y el PR |
| 5, falla visible | Código de salida distinto de 0, el registro en el journal y el estado de la unidad |
| 6, documentado con la reversa | `docs/INV-62-reentrenamiento.md`, con la instalación, la periodicidad y la reversa |
| 7, deseable: recupera la pendiente | `Persistent=true` en el temporizador |
| Agregado: evaluación de la receta | Sección 5, en MLflow y en docs, cumpla o no |

## 7. Pruebas

| Qué se prueba | Dónde |
| --- | --- |
| Sin datos nuevos: termina sin entrenar y registra el run | `notebooks/tests/test_reentrenamiento.py`, con datos sintéticos |
| Candidato aceptado y candidato rechazado por cada criterio | Ídem |
| MLflow sin responder: falla con código distinto de 0 | Ídem |
| Máscara de censura: enmascara solo la racha sin venta antes de una foto con stock ≤ 0, y nunca el stock negativo | Ídem |
| Estratos al corte: cabeza hasta el 50 % y medio hasta el 80 % del volumen | Ídem |
| Cortes walk-forward con purge | Ídem |
| Si el calendario entra: paridad de `features.py` con las funciones de la exploración | `ml_service/tests/` |
| Una corrida real de punta a punta disparada por el temporizador, y la reversa | Manual, documentada |

Cobertura de las pruebas del reentrenamiento: al menos 80 %.

## 8. Ruta

1. Estos requerimientos y el preregistro de la receta, en un commit y en MLflow antes de correr.
2. Las funciones del reentrenamiento (máscara, estratos, cortes y regla de promoción) con sus pruebas.
3. La evaluación de la receta: replicación del calendario, efecto de la máscara y simulación de la calibración adaptativa.
4. Si el calendario replica: `features.py` y su paridad.
5. El orquestador, la unidad y el temporizador, la corrida de punta a punta y la reversa.
6. La documentación. Después, con formulario: la ficha de Jira y Confluence. El viernes, los PR de INV-63 e INV-62.

## 9. Riesgos

- **Tiempo:** la historia vence el 20-nov y el sprint cierra ese día. Si el calendario no replica, el paso 4 no se hace.
- **WSL apagado:** sin «linger», el temporizador corre solo con una sesión abierta; recupera el disparo pendiente al abrir WSL.
- **Datos ya vistos:** la evaluación de la receta usa datos ya usados para diseñar y evaluar el motor. La confirmación limpia de la temporada
  alta queda preregistrada para las ventas de oct-2026 a ene-2027.
- **Disco:** cada corrida escribe una matriz de unos 30 MB fuera del repositorio; el orquestador borra las de corridas anteriores.

## 10. Pronóstico al día presente (agregado el 18-nov)

El usuario amplió el sprint: el pronóstico se hace desde hoy con el historial de ventas disponible. No hay carga diaria de ventas: los datos
llegan al 30-sep-2026 y hoy (18-nov) hay **49 días hábiles sin datos**. La sesión de INV-40 hace la parte de Vera (decir desde y hasta cuándo
cubre el pronóstico y la fecha de hoy) y consume los campos nuevos de la respuesta.

| Decisión | Qué se decidió | Origen |
| --- | --- | --- |
| **Alcance** | Todo el servicio de predicción opera a la fecha de operación: el pronóstico (pantalla de Predicciones y Vera), los traslados y las compras (también su calendario de pedidos). El stock sigue siendo el de la última foto de inventario: se declara como límite | Usuario, 18-nov |
| **Fecha de operación** | Por defecto, hoy en la zona horaria de Bogotá (nunca antes del último dato). Se puede fijar con la variable `FECHA_OPERACION` para pruebas y demostraciones | Usuario, 18-nov |
| **Ventana y features** | La ventana son los 15 días hábiles siguientes a la fecha de operación (calendario de `dim_tiempo`, sin los cierres programados). Las features se calculan con el historial hasta el último dato; el factor de calendario, con la ventana nueva | Técnica |
| **Respuesta** | El pronóstico dice el último dato (`fecha_datos`), la fecha de operación, la ventana (`ventana_desde` y `ventana_hasta`), los días hábiles sin datos (`dias_habiles_sin_datos`). `fecha_features` se conserva. El campo «lleva ajuste por desfase» se retiró al no entrar ningún ajuste | Técnica, coordinado con INV-40 |
| **Ajuste por desfase** | Antes de servirlo, se mide con el historial cuánto cambia la cobertura del cuantil de negocio cuando la ventana empieza varios días hábiles después del último dato. Si se sale más de 0,05 de su objetivo, se aplica un ajuste conformal por desfase (el mismo procedimiento de la calibración vigente) y la respuesta lo avisa | Usuario, 18-nov |
| **Caché del Core API** | La clave sigue siendo la fecha de la foto y las políticas; el tiempo de vida de 6 horas absorbe el cambio diario de la ventana. Se documenta | Técnica |

**Protocolo de la medición** (`notebooks/preregistro_desfase_2026.json`, registrado antes de correr):

- Desfases de 0, 15, 30, 45, 60, 75 y 90 días hábiles.
- El paquete vigente predice con las features de cada origen y se compara con la demanda de la ventana desplazada.
- Los ajustes se estiman con los orígenes de ene-abr 2026 y se evalúan con los de may-jul 2026, por rama y estrato.
- El ajuste entra para un desfase si la cobertura sin ajuste se sale más de 0,05 de su objetivo en la evaluación y el ajuste la devuelve
  dentro de la tolerancia.

**Resultado de la medición (18-nov):** no entra ningún ajuste. Hasta 90 días hábiles sin datos, las tres ramas quedan a menos de 0,05 de
su cobertura objetivo; con el desfase de hoy (49 días) la precisión de la mediana pasa de 0,41 a 0,44. Detalle en
`docs/INV-62-reentrenamiento.md`, sección 6.

**Límite de lo medido:** más allá de 90 días hábiles sin datos no hay medición. Con los datos al 30-sep-2026, ese día es el 29-dic-2026; si
para entonces no llegan ventas nuevas, el pronóstico sale de lo medido. El comportamiento en ese caso queda por decidir con el usuario.
