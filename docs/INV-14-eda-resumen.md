# INV-14 — EDA de priorización de SKU: resumen de resultados

Registra los resultados de correr la cadena `notebooks/01_calidad_y_panel.ipynb`
→ `05_sintesis.ipynb` contra el DW real de InventaIO (producido por
`etl_real/`, HU INV-61). Cada notebook lee mecánicamente los artefactos
del anterior (verificación de huella SHA-256 antes de consumir cada
insumo) y exporta sus decisiones a CSV/parquet — nada se transcribe a
mano de una corrida anterior; los números de este documento salen
directamente de `05_sintesis.ipynb`.

No cubre el ETL (INV-61, ya documentado en `docs/INV-61-inventario-real.md`)
ni la matriz de entrenamiento as-of/modelo baseline — eso es INV-15 e
INV-17 respectivamente.

## Alcance de las 5 notebooks

| # | Notebook | Qué decide |
|---|---|---|
| 01 | `01_calidad_y_panel.ipynb` | Calidad de datos, panel diario, ventana activa por par producto×sucursal |
| 02 | `02_regla_priorizacion.ipynb` | Las 7 condiciones de la regla de priorización de negocio → `es_prioritario` |
| 03 | `03_calendario_estacionalidad.ipynb` | Efectos de calendario confirmados estadísticamente, estacionalidad por categoría×sucursal |
| 04 | `04_demanda_y_baseline.ipynb` | Patrón de demanda (ADI/CV², Syntetos-Boylan), baseline WAPE por origen, riesgo de quiebre |
| 05 | `05_sintesis.ipynb` | Catálogo consolidado de features, recomendación de enfoque de modelado |

Catálogo activo: **4.414 productos** (`dim_producto`, ya con la doble
validación de inventario de INV-61), **10.805 pares** producto×sucursal
(`priorizacion_producto_sucursal.parquet`).

## 1. Catálogo de features de calendario (03 → 05)

11 de 13 eventos de calendario con efecto estadísticamente confirmado
(IC 95% no cruza 1.0) se incluyen; 2 se retiran (`Víspera de festivo`,
`Resaca de festivo` — IC cruza 1.0, sin efecto claro):

| Evento | Factor | IC 95% | Dirección |
|---|---|---|---|
| fin_de_anio | 2.53× | [2.06, 3.12] | sube |
| nochebuena_navidad | 1.63× | [1.32, 2.01] | sube |
| novena | 1.46× | [1.31, 1.62] | sube |
| enero_postnavidad | 1.40× | [1.23, 1.59] | sube |
| Semana Santa | 1.35× | [1.21, 1.51] | sube |
| Puente festivo | 1.34× | [1.22, 1.47] | sube |
| Inicio de mes (1-3) | 1.32× | [1.25, 1.39] | sube |
| Período de prima | 1.07× | [1.02, 1.12] | sube |
| Fin de mes (≥28) | 0.93× | [0.88, 0.98] | baja |
| Quincena (15-17) | 0.91× | [0.86, 0.96] | baja |
| Festivo | 0.87× | [0.80, 0.95] | baja |

5 de los 11 incluidos requieren cautela por evidencia limitada (IC
ancho): 4 son del bloque diciembre/enero (3 diciembres completos de
evidencia gracias a los datos de 2023 cerrados en INV-61) y 1 es Semana
Santa (evidencia limitada por duración corta del evento, no por el hueco
de datos).

## 2. Periodicidad semanal y anual

- **Ciclo semanal**: significativo a nivel negocio agregado (ACF lag7 =
  0.110 > umbral 0.061) pero **fuerza baja-moderada** (STL = 0.085) —
  y **seasonal-naive pierde contra media móvil en los 4 orígenes** de
  backtesting a nivel SKU (sección 6). La periodicidad real es más débil
  a nivel SKU que a nivel agregado.
- **Interacción categoría×sucursal**: real, no ruido de muestra (rango
  observado 0.953 vs. referencia de ruido 0.261, >1.5×) — se incluye la
  interacción, no un índice agregado solo por categoría.
- **Término anual (Fourier 365)**: generaliza fuera de muestra
  (leave-one-year-out 2023-2024→2025 sobre unidades: MAE estacional
  2.704 vs. MAE plano 4.382, mejora 38.3%) — se incluye.

## 3. Precio y devoluciones

- **Precio (proxy de descuento)**: se retira de prioridad alta — el
  proxy vende *menos* con descuento (efecto contrario al esperado,
  43.5 u/día con vs. 46.3 u/día sin), probablemente mezcla cambios de
  referencia/proveedor. Queda como feature exploratoria de baja prioridad.
- **Devoluciones**: se incluye como feature de riesgo (nivel 2) — 18.8%
  de las devoluciones son de productos perecederos/refrigerados vs.
  11.8% de esas categorías en el catálogo.

## 4. Patrón de demanda y racha de ceros

El subconjunto prioritario está **dominado por demanda intermitente** a
grano diario: 71.1% intermitente, 3.3% suave (18.0% lumpy, 4.6% errático).
A grano semanal "suave" sube a 27.6%, pero intermitente sigue siendo
mayoría (52.7%). El enrutamiento de modelo no puede asumir una sola
familia para todo el conjunto.

La racha máxima de ceros del grupo `solo_6_o_7` (prioridad por
volumen/rotación, sin razón estructural para rachas largas) es mayor que
la de los no-prioritarios (mediana 6 vs. 0 días) — evidencia directa de
que el desabastecimiento se concentra en los productos que al negocio le
importa reponer, no solo composición por perecederos/temporada.

## 5. Contrafactual ABC

La regla de negocio captura **51.4%** del valor histórico con 919
productos; un ABC puro del mismo tamaño de catálogo captura 79.4%. Los
570 productos que **solo** la regla prioriza (el ABC no los tomaría)
aportan apenas **4.4%** del valor — confirma que esos criterios (riesgo
operativo: perecederos, espacio, temporada) no son de maximización de
ingreso. Un modelo optimizado solo por WAPE/valor esperado subestimaría
sistemáticamente su prioridad.

## 6. Baseline: piso de comparación (`piso_baseline_por_patron.csv`)

Seasonal-naive **no le gana** a media móvil en ningún origen (0/4) — el
piso de comparación para cualquier modelo candidato es **media móvil**:

| Patrón | WAPE piso (diario) | WAPE piso (horizonte 15d) |
|---|---|---|
| suave | 0.445 | 0.199 |
| erratico | 0.686 | 0.360 |
| lumpy | 1.091 | 0.572 |
| intermitente | 1.297 | 0.700 |

Peor origen de pronóstico: `semana_santa` (piso WAPE 0.888) — coincide
con el efecto de calendario más fuerte fuera de diciembre (1.35×). Mejor
origen: `diciembre_alto`. Un modelo validado solo en meses ordinarios se
cae justo donde más le importa al negocio.

## 7. Catálogo consolidado (`features_recomendadas.csv`)

27 features catalogadas: 21 a incluir (16 nivel 1, 4 nivel 2, 1 de
enrutamiento), 3 a retirar (2 eventos de calendario sin efecto + precio).
Columna `origen_decision` distingue `evidencia` (depende de un número
calculado en la cadena) de `estandar` (features que entran por diseño).

## 8. Recomendación de enfoque de modelado

- **Nivel 1 (demanda)**: enrutamiento por patrón ADI/CV² (Syntetos-Boylan).
  Demanda suave → gradient boosting global (LightGBM/XGBoost), debe
  superar el piso 0.445 (y en particular el de `semana_santa`, 0.888).
  Demanda intermitente/errática/lumpy (mayoría del conjunto) → Croston/SBA
  o TSB, con el índice estacional categoría×sucursal como feature en vez
  de lags cortos.
- **Nivel 2 (riesgo de quiebre)**: clasificador de
  `P(stock < demanda proyectada 7/15 días)` usando `dias_cobertura`,
  `lead_time_dias`, `racha_max_ceros_alta_frecuencia` y tasa de
  devolución por categoría (todas disponibles).
- **Métrica**: pinball loss en cuantiles altos (0.8-0.95) para el
  pronóstico; WAPE (diario y de ventana acumulada) contra el piso de
  `piso_baseline_por_patron.csv`, no contra el promedio general.
- **Validación**: walk-forward con folds que incluyan explícitamente
  diciembre Y Semana Santa — nunca solo meses ordinarios.

Esta recomendación de nivel 1 es la base de la HU INV-15 (feature
engineering) e INV-17 (modelo baseline), que ya incorporan el enrutamiento
ADI/CV² y un ensamble Tweedie+LightGBM en las ramas suaves (ver
`docs/INV-17-modelo-baseline.md`).

## Verificación de esta corrida

```bash
cd notebooks
$JUPYTER nbconvert --to notebook --execute --inplace 0N_*.ipynb   # 01..05, en orden
```

`huella_01.json` … `huella_05.json` se generan en `data/processed_real/`
(raíz del repo, `notebooks/common_priorizacion.py::DW`) y cada notebook
verifica la huella del anterior antes de continuar — si algo falla ahí,
el dato de entrada cambió desde que se generó la huella.

## Pendiente / fuera de alcance de esta HU

1. Confirmar con el negocio el umbral de frecuencia de la condición 7
   (`PARAMS['UMBRAL_FRECUENCIA_COND7']`) como reemplazo del "top 50" fijo.
2. Prototipar el enrutamiento ADI/CV² → familia de modelo con backtesting
   real sobre los 4 orígenes, no un fold único (hecho parcialmente en
   INV-17, ver su doc).
3. Revisar con el negocio los falsos positivos/negativos de la condición 5.
4. Si se consigue más historia de 2023 (o se agrega 2022, fase futura ya
   decidida), reejecutar 03-05 — varias decisiones dependen de 3 años de
   evidencia, no más.
5. Renombrar `sensible_a_especificacion` en `efectos_calendario.csv` —
   hoy mide ancho de IC, no sensibilidad real a la especificación del
   modelo (se perdió esa prueba al migrar a la regresión conjunta).
