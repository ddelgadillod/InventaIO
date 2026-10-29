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

Catálogo activo: **4.449 productos** (`dim_producto`, ya con la doble
validación de inventario de INV-61), **11.135 pares** producto×sucursal
(`priorizacion_producto_sucursal.parquet`).

> **Corrida con datos de 2022 (2026-09-24).** Las cifras de este documento
> corresponden a la re-ejecución de 01-05 tras sumar 2022 al DW
> (`fix/datos-2022-etl-dw`). El histórico pasa de 1.060 a 1.362 días
> hábiles. Hay un hueco genuino de 2 meses (noviembre-diciembre 2022, el
> negocio no subió esos reportes) además del de febrero 2023;
> `PARAMS['MESES_INCOMPLETOS'] = ["2022-11", "2022-12", "2023-02"]`.
> Cambios de conclusión respecto a la corrida anterior: `Período de prima`
> pasa de "incluir" a "retirar" (su IC ahora toca 1.0); Semana Santa deja
> de figurar como evento de evidencia limitada; el catálogo de features
> pasa de 21 a 23 a incluir.

## 1. Catálogo de features de calendario (03 → 05)

10 de 13 eventos de calendario con efecto estadísticamente confirmado
(IC 95% no cruza 1.0) se incluyen; 3 se retiran (`Víspera de festivo`,
`Resaca de festivo`, `Período de prima` — IC cruza o toca 1.0, sin efecto
claro):

| Evento | Factor | IC 95% | Dirección | Años de evidencia |
|---|---|---|---|---|
| fin_de_anio | 2.56× | [2.09, 3.14] | sube | 3 |
| nochebuena_navidad | 1.62× | [1.32, 1.99] | sube | 3 |
| novena | 1.48× | [1.33, 1.64] | sube | 3 |
| Semana Santa | 1.36× | [1.24, 1.50] | sube | 4 |
| enero_postnavidad | 1.33× | [1.19, 1.49] | sube | 4 |
| Puente festivo | 1.33× | [1.23, 1.44] | sube | 4 |
| Inicio de mes (1-3) | 1.28× | [1.22, 1.35] | sube | 4 |
| Fin de mes (≥28) | 0.93× | [0.89, 0.97] | baja | 4 |
| Quincena (15-17) | 0.89× | [0.85, 0.94] | baja | 4 |
| Festivo | 0.88× | [0.82, 0.95] | baja | 4 |

3 de los 10 incluidos requieren cautela por evidencia limitada (IC
ancho): `fin_de_anio`, `nochebuena_navidad` y `novena`, todos del bloque
de diciembre, con solo 3 diciembres completos de evidencia (2023, 2024,
2025; diciembre 2022 no tiene datos). Los 3 aparecen marcados
`sensible_a_especificacion = True` en `efectos_calendario.csv`, que hoy
mide ancho de IC (ver pendiente 5).

## 2. Periodicidad semanal y anual

- **Ciclo semanal**: significativo a nivel negocio agregado (ACF lag7 =
  0.110 > umbral 0.054) pero **fuerza baja-moderada** (STL = 0.083) —
  y **seasonal-naive pierde contra media móvil en los 4 orígenes** de
  backtesting a nivel SKU (sección 6). La periodicidad real es más débil
  a nivel SKU que a nivel agregado.
- **Interacción categoría×sucursal**: real, no ruido de muestra (rango
  observado 0.975 vs. referencia de ruido 0.203, ~4.8×) — se incluye la
  interacción, no un índice agregado solo por categoría.
- **Término anual (Fourier 365)**: generaliza fuera de muestra
  (leave-one-year-out 2023-2024→2025 sobre unidades: MAE estacional
  2.704 vs. MAE plano 4.382, mejora 38.3%) — se incluye.

## 3. Precio y devoluciones

- **Precio (proxy de descuento)**: se retira de prioridad alta — el
  proxy vende *menos* con descuento (efecto contrario al esperado,
  40.5 u/día con vs. 47.1 u/día sin), probablemente mezcla cambios de
  referencia/proveedor. Queda como feature exploratoria de baja prioridad.
- **Devoluciones**: se incluye como feature de riesgo (nivel 2) — 19.2%
  de las devoluciones son de productos perecederos/refrigerados vs.
  11.7% de esas categorías en el catálogo.

## 4. Patrón de demanda y racha de ceros

El subconjunto prioritario (929 productos) está **dominado por demanda
intermitente** a grano diario: 70.3% intermitente, 3.2% suave (18.9%
lumpy, 4.8% errático, 2.9% sin datos). A grano semanal "suave" sube a
25.7%, pero intermitente sigue siendo mayoría (54.3%). El enrutamiento
de modelo no puede asumir una sola familia para todo el conjunto.

La racha máxima de ceros del grupo `solo_6_o_7` (prioridad por
volumen/rotación, sin razón estructural para rachas largas) es mayor que
la de los no-prioritarios (mediana 7 vs. 1 días) — evidencia directa de
que el desabastecimiento se concentra en los productos que al negocio le
importa reponer, no solo composición por perecederos/temporada.

## 5. Contrafactual ABC

La regla de negocio captura **52.0%** del valor histórico con 929
productos; un ABC puro del mismo tamaño de catálogo captura 79.9%. Los
571 productos que **solo** la regla prioriza (el ABC no los tomaría)
aportan apenas **4.3%** del valor — confirma que esos criterios (riesgo
operativo: perecederos, espacio, temporada) no son de maximización de
ingreso. Un modelo optimizado solo por WAPE/valor esperado subestimaría
sistemáticamente su prioridad.

## 6. Baseline: piso de comparación (`piso_baseline_por_patron.csv`)

Seasonal-naive **no le gana** a media móvil en ningún origen (0/4) — el
piso de comparación para cualquier modelo candidato es **media móvil**:

| Patrón | WAPE piso (diario) | WAPE piso (horizonte 15d) |
|---|---|---|
| suave | 0.445 | 0.198 |
| erratico | 0.689 | 0.367 |
| lumpy | 1.086 | 0.565 |
| intermitente | 1.294 | 0.699 |

Peor origen de pronóstico según el WAPE naive: `semana_santa` (naive
1.11, media móvil 0.889) — coincide con el efecto de calendario más
fuerte fuera de diciembre (1.36×). Mejor origen: `diciembre_alto`
(naive 1.00). Ojo: medido solo con la media móvil, el origen con mayor
WAPE es `ordinario_2` (0.944), no `semana_santa`; el texto de la
síntesis (05) toma el peor origen por naive. Un modelo validado solo en
meses ordinarios se cae justo donde más le importa al negocio.

## 7. Catálogo consolidado (`features_recomendadas.csv`)

27 features catalogadas: 23 a incluir (17 nivel 1, 5 nivel 2, 1 de
enrutamiento), 4 a retirar (3 eventos de calendario sin efecto + precio).
Columna `origen_decision` distingue `evidencia` (depende de un número
calculado en la cadena) de `estandar` (features que entran por diseño).

## 8. Recomendación de enfoque de modelado

- **Nivel 1 (demanda)**: enrutamiento por patrón ADI/CV² (Syntetos-Boylan).
  Demanda suave → gradient boosting global (LightGBM/XGBoost), debe
  superar el piso 0.445 (y en particular el de `semana_santa`, 0.889).
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
3. Revisar con el negocio los falsos positivos/negativos de la condición 5
   (esta corrida: 13 falsos positivos y 22 falsos negativos).
4. 2022 ya está incorporado (esta corrida). Los eventos de diciembre
   siguen con solo 3 años de evidencia porque noviembre-diciembre 2022 es
   un hueco genuino; si el negocio consigue esos reportes, reejecutar 03-05.
5. Renombrar `sensible_a_especificacion` en `efectos_calendario.csv` —
   hoy mide ancho de IC, no sensibilidad real a la especificación del
   modelo (se perdió esa prueba al migrar a la regresión conjunta).
