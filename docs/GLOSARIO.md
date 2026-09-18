# Glosario — técnicas y términos del pronóstico de demanda

Referencia rápida de los términos técnicos usados en `docs/METODOLOGIA-EDA-MODELADO.md`,
`docs/INV-60-*.md` a `docs/INV-63-*.md`, y en las notebooks 01-08. Ordenado
temáticamente, no alfabéticamente — sigue aproximadamente el orden en que
cada concepto aparece en la cadena.

## Datos y calidad

**Grano (temporal)** — la unidad de tiempo sobre la que se agrega una
métrica: diario, semanal, mensual. Un grano más fino (diario) tiene más
ruido pero cubre menos catálogo con confianza estadística; uno más
grueso (mensual) suaviza el ruido pero pierde capacidad de reacción.

**Hueco de calendario** — un día sin ninguna venta registrada en todo el
negocio. Se clasifica en domingo, festivo, o **residuo sin explicar**
(ni domingo ni festivo — indica un reporte de origen faltante, no un
día real sin actividad).

**Día hábil** — día que NO es un hueco de calendario (ni domingo ni
festivo ni residuo). El calendario hábil (`calendario_habil.csv`) es el
eje temporal sobre el que se miden frecuencias, rachas y ventanas en
toda la cadena — evita que un domingo cuente como "día sin venta" al
mismo nivel que un día hábil real sin venta.

**Ventana activa** — el rango entre la primera y la última venta real
observada de un par producto×sucursal. Un producto "vivo" para efectos
del pronóstico tiene ventas recientes dentro de esa ventana; uno
"muerto" (descontinuado) se excluye para no arrastrarlo como si
siguiera activo.

## Regla de priorización y ABC

**ABC (análisis)** — clasificación de productos por su contribución
acumulada al valor de venta (A = alto valor, B = medio, C = bajo).
**ABC contrafactual** en este proyecto: comparar qué productos
capturaría un ABC puro por valor contra los que captura la regla de 7
condiciones del negocio — para medir si la regla aporta algo que el ABC
no vería (sí: productos de bajo valor pero alta criticidad operativa,
como papel higiénico).

**Condiciones 1-7 (regla de priorización)** — criterios del negocio para
marcar un producto como prioritario: espacio en bodega, perecedero,
refrigerado, papel higiénico, temporada, top-50 por sucursal, frecuencia
de venta. Las condiciones 6 y 7 se excluyen como feature del modelo por
**fuga temporal** (ver abajo) — dependen de rankear el histórico
completo.

## Calendario y estacionalidad

**Efecto de calendario** — el multiplicador sobre la venta esperada que
tiene un evento (festivo, Semana Santa, quincena, bloque de diciembre),
estimado con una **regresión conjunta OLS** sobre todas las banderas de
calendario a la vez (no una por una) — así el efecto de un evento no se
confunde con el de otro que ocurre en fechas cercanas.

**Intervalo de confianza (IC) / "cruza 1.0"** — si el IC del efecto
estimado incluye 1.0 (sin efecto), el evento **no** se considera
confirmado, aunque el número puntual sugiera un efecto — evita tratar
ruido de muestreo como una señal real.

**`factor_calendario_ventana`** — feature única que resume el efecto de
calendario esperado en TODA la ventana de pronóstico de 15 días (no un
día puntual), porque el target del modelo es una demanda acumulada, no
diaria. Ver `docs/INV-63-correccion-factor-calendario.md` para el bug
que dejaba 8 de 11 eventos confirmados fuera de esta feature.

**Leave-one-year-out (LOYO)** — validación que entrena con N-1 años y
prueba sobre el año restante, para medir si un patrón estacional
generaliza de un año a otro (no solo dentro del mismo año).

## Patrón de demanda

**ADI (Average Demand Interval)** — el intervalo promedio, en días, entre
dos ventas consecutivas de un par producto×sucursal. ADI alto = demanda
poco frecuente (intermitente).

**CV² (Coeficiente de Variación al cuadrado)** — la varianza relativa del
TAMAÑO de la demanda cuando sí ocurre (no de si ocurre o no). CV² alto =
tamaños de venta muy variables cuando hay venta.

**Clasificación de Syntetos-Boylan (4 cuadrantes ADI/CV²)** — cruza ADI y
CV² contra umbrales de corte para clasificar la demanda en 4 patrones:
**suave** (ADI bajo, CV² bajo — frecuente y estable), **errático** (ADI
bajo, CV² alto — frecuente pero de tamaño variable), **intermitente**
(ADI alto, CV² bajo — esporádica pero de tamaño estable), **lumpy** (ADI
alto, CV² alto — esporádica Y de tamaño variable, la más difícil de
pronosticar). Este proyecto agrupa errático+lumpy con intermitente al
enrutar a familia de modelo (05, corrección D3), aunque conserva los 4
cuadrantes en el análisis.

**Racha de ceros** — la cantidad máxima de días hábiles consecutivos sin
venta para un par. Junto con la frecuencia de venta, ayuda a decidir si
un par está realmente "vivo" o si su historial reciente es puro ruido.

## Baseline y métricas de error

**WAPE (Weighted Absolute Percentage Error)** — `sum(|y - ŷ|) / sum(|y|)`.
Se usa en vez de MAPE porque no se rompe cuando `y=0` (frecuente en
demanda intermitente) y pondera por volumen real, no por porcentaje de
error de cada fila por igual.

**Piso / baseline** — el desempeño de un método simple (media móvil,
naive estacional) medido con el MISMO protocolo que un modelo candidato,
para que "superar el piso" sea una comparación justa, no una cifra
aislada. En este proyecto, la media móvil de 60 días fue el piso oficial
tras ganarle 4/4 al naive estacional.

**Naive estacional** — repetir el valor observado el mismo día de la
semana en el ciclo anterior, como pronóstico. Perdió contra la media
móvil en las 4 pruebas de este proyecto.

## Ingeniería de features

**Fuga temporal (data leakage)** — cuando una feature usada para
entrenar contiene información que, en producción, no estaría disponible
en el momento real del pronóstico. La forma más común aquí: calcular una
estadística (frecuencia, ranking) sobre el histórico COMPLETO en vez de
solo sobre el pasado relativo a cada origen de pronóstico.

**Feature "as-of"** — una feature recalculada usando SOLO datos
anteriores a una fecha de corte (`train_end`) específica, en vez de una
sola vez sobre todo el dataset. Es la técnica central para evitar fuga
temporal en pronóstico de series de tiempo.

**Walk-forward / folds expansivos** — protocolo de validación donde cada
fold entrena con TODO el pasado disponible hasta ese punto y prueba en
el período inmediatamente siguiente (`train = folds anteriores, test =
fold actual`), nunca al revés — simula cómo el modelo se usaría en
producción real. Distinto de un split aleatorio (que filtraría
información temporal) o de k-fold estándar (que no respeta el orden del
tiempo).

**Origen (de pronóstico)** — la fecha desde la cual se genera una
predicción hacia adelante (`fecha_origen`). Los orígenes de
entrenamiento se espacian por el horizonte de pronóstico (15 días
hábiles) para que las ventanas objetivo no se solapen.

**Cold start** — un par producto×sucursal sin suficiente historia previa
al origen para calcular sus features as-of de forma confiable. Se
descarta explícitamente (reportando cuánto se pierde), no se imputa.

**Target acumulado** — la variable objetivo del modelo,
`target_demanda_15d`: la SUMA de unidades vendidas en los 15 días
hábiles siguientes al origen (no la demanda de un solo día).

## Familias de modelo

**LightGBM** — implementación de *gradient boosting* sobre árboles de
decisión (ensamble secuencial: cada árbol nuevo corrige los errores de
los anteriores). Flexible, pero necesita bastante dato para no
sobreajustar.

**Regresión cuantílica (`objective='quantile'`)** — en vez de predecir
la media (como una regresión estándar), predice un CUANTIL específico de
la distribución condicional (ej. la mediana = cuantil 0.5, o el cuantil
0.89 para una alerta conservadora de negocio). LightGBM lo soporta de
forma nativa cambiando la función de pérdida.

**GLM (Modelo Lineal Generalizado)** — regresión lineal donde la
variable objetivo puede seguir una distribución distinta a la normal
(Poisson, Tweedie, etc.) vía una función de enlace. Mucho más simple que
un ensamble de árboles — con poca muestra, esa simplicidad generaliza
mejor.

**Distribución/Regresión Tweedie** — familia de distribuciones
parametrizada por `power` que interpola entre Normal (`power=0`),
Poisson (`power=1`) y Gamma (`power=2`) — útil para variables no
negativas, con posible masa en cero. En este proyecto, el `power=0`
ganador equivale en la práctica a una regresión Ridge (lineal
regularizada) sobre el target crudo, no a un modelo de conteo
propiamente dicho.

**Regularización (`alpha`, `reg_alpha`/`reg_lambda`, L1/L2)** — penalización
sobre el tamaño de los coeficientes/hojas de un modelo, para evitar que
se ajuste al ruido de la muestra de entrenamiento en vez de a la señal
real. Más regularización = modelo más simple = más sesgo pero menos
varianza.

**Sobreajuste (overfitting)** — cuando un modelo aprende patrones
específicos de la muestra de entrenamiento (incluyendo su ruido) que no
generalizan a datos nuevos. La señal clásica: el modelo se ve muy bien
en entrenamiento pero mal en un conjunto de prueba independiente — es
justo lo que se diagnosticó en las ramas suaves con los hiperparámetros
por defecto de LightGBM.

**Croston / SBA (Syntetos-Boylan Approximation)** — método clásico para
pronosticar demanda intermitente: en vez de modelar la demanda día a
día, estima por separado el TAMAÑO de la demanda cuando ocurre y el
INTERVALO entre ocurrencias, y corrige un sesgo conocido del método
original de Croston (SBA aplica el factor `1 - alpha/2`). Se probó para
la rama intermitente de este proyecto y perdió contra la media móvil —
hallazgo negativo, documentado, no usado en producción.

**Ensamble (blend)** — combinar las predicciones de 2+ modelos
(típicamente un promedio ponderado) para reducir la varianza del error,
aprovechando que distintos modelos no suelen equivocarse en las mismas
filas. Requiere que los modelos base tengan errores no perfectamente
correlacionados para que aporte algo sobre el mejor modelo individual.

**Modelo hurdle (de dos partes)** — arquitectura para variables con masa
puntual en cero: un clasificador estima `P(y > 0)`, y un segundo modelo
(entrenado SOLO sobre las observaciones positivas) estima la magnitud
condicional a que haya demanda. Se probó y se descartó en este proyecto
para `suave_perecedero` porque la premisa (que hubiera ceros en el
target) resultó falsa para esa rama.

**Reconciliación jerárquica / pooling parcial** — técnica para compartir
información estadística entre series relacionadas (ej. SKU dentro de
una misma categoría) en vez de ajustar cada una de forma completamente
independiente — reduce la varianza en series con poca muestra individual
"tomando prestada" señal de series relacionadas con más historia.
Propuesta como siguiente paso para las ramas suaves, no implementada
todavía en este proyecto.

## Calibración e incertidumbre

**Cuantil de negocio (`pred_q_negocio`)** — la predicción al nivel de
cuantil que refleja la aversión al riesgo del negocio (ej. 0.89 para no
perecederos: mejor sobre-pronosticar que quedarse corto; 0.17 para
perecederos: el costo de sobrante pesa más que el de faltante). Se
deriva de una función de costo asimétrica (ver `cuantil_optimo` más
abajo).

**Cuantil óptimo bajo costos asimétricos** — fórmula `Cu / (Cu + Co)`
(problema del "newsvendor" / vendedor de periódicos), donde `Cu` es el
costo de pronosticar de menos (quiebre) y `Co` el costo de pronosticar
de más (sobrante/merma). Determina a qué cuantil apuntar según qué error
sale más caro para el negocio.

**Cobertura empírica** — la fracción real de casos donde el valor
observado quedó por debajo de la predicción de un cuantil. Si se pidió
el cuantil 0.89, la cobertura empírica debería acercarse a 0.89 — si se
aleja mucho, el modelo está **mal calibrado**: el número que reporta
como "cuantil 0.89" no se comporta como tal.

**Calibración** — qué tan bien coincide la cobertura empírica con el
nivel de cuantil pedido. Un modelo puede tener buen WAPE (buen pronóstico
puntual) y aun así estar mal calibrado en sus cuantiles — son
propiedades distintas del modelo.

**Recalibración conformal / Split-CQR (Conformalized Quantile
Regression)** — método POST-HOC, agnóstico al modelo, para corregir la
calibración de un cuantil: se separa una porción de los datos de
entrenamiento (`calib`) nunca usada para ajustar el modelo, se mide
cuánto se equivocó el modelo ahí, y se usa ese error medido para
desplazar la predicción en datos nuevos. No asume nada sobre la forma de
la distribución del error — por eso funcionó donde otros intentos
(basados en supuestos sobre la forma de los residuales) fallaron en este
proyecto.

**Pinball loss** — la función de pérdida propia de la regresión
cuantílica: penaliza distinto un error por exceso que por defecto, según
el cuantil objetivo. Es la métrica que sí "sabe" que un cuantil de 0.89
debería estar mal calibrado si se compara con MAE/WAPE estándar (que
asumen implícitamente la mediana).

## Validación y buenas prácticas del proyecto

**Selección sobre el conjunto de evaluación (search/selection bias)** —
riesgo de que una mejora medida sea, en parte, el resultado de haber
probado muchas configuraciones y quedarse con la que mejor le fue en
ESE conjunto de prueba específico — no necesariamente una mejora que se
sostenga en datos genuinamente nuevos. Es la razón por la que este
proyecto valida con folds excluidos, semillas alternativas, y documenta
explícitamente cuándo una "victoria" depende de un solo fold (ver
`docs/INV-62-inventario-real.md` §4, ronda 4).

**Huella (fingerprint)** — hash SHA-256 de los archivos de entrada/salida
de cada notebook (`huella_0N.json`), que el siguiente notebook de la
cadena verifica antes de leer sus artefactos — detecta si algo
corriente arriba cambió sin haber re-ejecutado lo que depende de ello.

**MLflow / experimento / run** — sistema de registro de experimentos de
modelado: un **experimento** agrupa **runs** (corridas individuales),
cada una con sus parámetros, métricas y metadatos, consultables después
sin tener que volver a correr nada. En este proyecto, cada ronda de
búsqueda de hiperparámetros/modelo tiene su propio experimento.

**Optuna / TPE (Tree-structured Parzen Estimator)** — librería y
algoritmo de búsqueda BAYESIANA de hiperparámetros: en vez de probar
combinaciones al azar (grid/random search) o exhaustivamente, usa los
resultados de los intentos anteriores para decidir qué combinación
probar a continuación de forma más informada — más eficiente con el
mismo presupuesto de intentos.
