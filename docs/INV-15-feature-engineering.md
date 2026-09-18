# INV-15 — Feature engineering: diagnóstico de Nivel 2 y matriz as-of

Registra los resultados de correr `notebooks/06_diagnostico_inventario.ipynb`
y `notebooks/07_matriz_as_of.ipynb` contra el DW real de InventaIO,
consumiendo el catálogo de features de la síntesis (INV-14,
`docs/INV-14-eda-resumen.md`). Construye la matriz de entrenamiento sin
fuga temporal (`matriz_as_of.parquet`) que consume el modelo baseline
(INV-17, `docs/INV-17-modelo-baseline.md`).

## 1. `06_diagnostico_inventario.ipynb` — ¿existe el Nivel 2?

Es una **compuerta**, no un paso de modelado: decide si el clasificador
de riesgo de quiebre (Nivel 2) es entrenable con el inventario real
disponible, o si hay que replantearlo como regla determinística.

El inventario real (`fact_inventario.csv`, INV-61) es una **foto a una
sola fecha** (2025-12-31, 11.035 filas), no una serie diaria. Esto
degrada la prueba original de dos formas distintas, ambas verificadas
explícitamente:

- **Prevalencia por umbral** (`dias_cobertura <= N`): technically
  "viable" — con umbral 0 ya hay 9.6% de prevalencia por fila/par-mes,
  muy por encima del piso mínimo (0.5%).
- **Pero la densidad del panel es 0.09%** (11.035 filas observadas de
  un universo de 10.805 pares × 1.060 días hábiles) — muy por debajo
  del piso `DENSIDAD_MINIMA = 0.05` (5%) agregado explícitamente en
  esta sesión. Con una sola fecha de corte, la prevalencia alta que
  parece "viable" en la sección 3 no tiene extensión temporal real para
  sostener un target de ventana de 15 días hábiles — es señal de un solo
  día, no de una serie.
- Prueba adicional de honestidad del dato: la venta del día siguiente es
  **similar** entre pares con y sin registro de inventario ese día
  (media 4.3 vs. 2.9 unidades) — la ausencia de registro no está
  fuertemente correlacionada con quiebre, así que tampoco hay un atajo
  de imputación que rescate la densidad.

**Veredicto**: `nivel2_supervisado = false` (`diagnostico_inventario.json`).
El Nivel 2 queda planteado como **regla determinística** sobre el
pronóstico cuantílico del Nivel 1 (`P(demanda_15d > stock_actual)`), no
como modelo entrenado — exactamente la salida de diseño prevista si esta
compuerta daba negativo. Con el inventario simulado anterior (antes de
INV-61) esta compuerta daba `true`; la diferencia es la limitación real
del dato, no un error de esta corrida.

## 2. `07_matriz_as_of.ipynb` — matriz de entrenamiento sin fuga temporal

Corrige 6 problemas estructurales de un intento previo
(`feature_engineering.ipynb`, no versionado en este repo), cada uno
anotado en su celda: split de fold roto (A2), `fillna(0)` que
etiquetaba "sin registro" como "sin quiebre" (A4), `shift` desalineado
del calendario hábil (B1), ventanas solapadas en 14 de 15 orígenes (B3),
ausencia total de features de calendario (C1), y filtro de fecha inerte
que nunca se activaba (`es_fecha_valida`).

### Diseño de validación: 5 folds expansivos reales

Cada fold cubre uno de los 4 orígenes de referencia
(`ordinario_1`/`ordinario_2`/`semana_santa`/`diciembre_alto`) para que
el resultado sea comparable con el piso de INV-14. El fold 1 solo
entrena, nunca se evalúa contra sí mismo.

### Corrección del filtro de fecha (empalme, no validez)

El filtro anterior (`es_fecha_valida`) nunca podía activarse — el
calendario hábil ya excluye los días sin venta, así que ninguna ventana
podía "caer" en un día inexistente. El riesgo real es el opuesto: una
ventana de 15 días hábiles que atraviesa un bloque de días faltantes
(ej. el hueco de 2023-02) suma demanda de dos períodos como si fueran
contiguos. Se reemplazó por una verificación de **span natural** — 29
orígenes se descartan por empalme o por horizonte incompleto (14 en
2023-01, 15 en 2025-12, ambos por cercanía a los bordes del histórico).

### `factor_calendario_ventana` — ya con el fix de INV-63 incluido

Esta notebook nunca tuvo la versión con el bug (mapeo por heurístico de
texto que solo matcheaba 3 de 11 eventos confirmados) — se portó
directamente con `EVENTO_A_CONDICION`, el mapeo explícito verificado
contra las columnas/valores reales de `calendario_eventos.csv`, con un
`assert` que detiene la ejecución si algún evento confirmado queda sin
mapear. En esta corrida: **11 de 11 eventos mapeados**,
`factor_calendario_ventana` con media 1.080, rango [0.974, 1.683].

### Matriz final

| Etapa | Filas |
|---|---|
| Matriz cruda (5 folds × orígenes espaciados) | 486.225 |
| Tras descartar cold start (`frecuencia_as_of < 30`) | 228.823 + 257.402 descartadas (52.9%) |
| Tras descartar lags incompletos | 0 adicionales |
| **Matriz final (`matriz_as_of.parquet`)** | **228.823** |

Las filas descartadas por cold start son mayoritariamente `intermitente`
(67.7%) y `sin_datos` (28.3%) — coherente con productos de baja rotación
que aún no acumulan 30 días de historia en el `train_end` de un fold
temprano, no una pérdida sesgada hacia un patrón de negocio.

Distribución por fold y familia de modelo (enrutamiento ADI/CV², dos
ramas: `suave` vs. `intermitente`, que agrupa erratico/lumpy/intermitente):

| Fold | intermitente | suave |
|---|---|---|
| 1 | 20.245 | 560 |
| 2 | 56.485 | 1.404 |
| 3 | 25.255 | 510 |
| 4 | 53.060 | 1.020 |
| 5 | 69.216 | 1.068 |

### Piso interno (mismas filas que verá el modelo)

`piso_interno_por_patron.csv` — a diferencia del piso de INV-14 (otro
universo, otros orígenes, columna diaria no comparable con un target
acumulado), este se calcula sobre exactamente las mismas filas de la
matriz final:

| Patrón | WAPE naive | WAPE media móvil |
|---|---|---|
| suave | 0.214 | **0.165** |
| erratico | 0.345 | 0.268 |
| lumpy | 0.573 | 0.496 |
| intermitente | 0.598 | 0.505 |

Media móvil gana en los 4 patrones — es el piso que el modelo baseline
(INV-17) debe superar, no el piso diario de INV-14.

### Nivel 2: no se construye target

Como el 06 concluyó `nivel2_supervisado = false`, esta notebook no
construye `target_quiebre_binario` — lo confirma explícitamente en su
salida, sin fallback silencioso a `fillna(0)`.

## Verificación de esta corrida

```bash
cd notebooks
$JUPYTER nbconvert --to notebook --execute --inplace 06_diagnostico_inventario.ipynb
$JUPYTER nbconvert --to notebook --execute --inplace 07_matriz_as_of.ipynb
```

`data/processed_real/huella_06.json` y `huella_07.json` se generan;
`07` verifica la huella de `01`, `02`, `03` y `06` antes de construir la
matriz. Invariantes verificadas dentro de `07` (todas con `assert`, no
solo advertencia): sin nulos en el target, sin targets negativos, sin
solapes de ventana no justificados, features as-of constantes dentro de
cada fold, ninguna bandera con fuga temporal (`cond6`/`cond7`/`es_prioritario`)
llegó a la matriz.

## Pendiente / fuera de alcance de esta HU

- El modelo baseline que consume esta matriz (`08_nivel1_demanda.ipynb`)
  es la HU INV-17.
- Si en el futuro se consigue una serie de inventario con más de una
  fecha, reevaluar la compuerta de Nivel 2 (`DENSIDAD_MINIMA = 0.05` está
  puesto para esa hipótesis, no está afinado contra un segundo caso real).
- Una validación con un corte de folds completamente nuevo (no solo
  excluir el fold 5 del análisis existente) requeriría reconstruir esta
  matriz con fronteras de fold distintas — no hecho aquí.
