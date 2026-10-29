# INV-17 — Modelo baseline de Nivel 1 (pronóstico de demanda)

> **Versión corregida (purge).** Las cifras de este documento se recalcularon con el entrenamiento walk-forward **purgado**:
> antes, las últimas filas de entrenamiento de cada fold tenían ventanas objetivo de 15 días que caían dentro del periodo de
> prueba (20% del entrenamiento del fold 2, 3-6% en los demás), lo que inflaba el desempeño del modelo frente al piso. Los
> números de versiones anteriores de este documento (p. ej. 0.416 / 0.182 / 0.150, y los de las rondas de búsqueda
> INV-62/63 en MLflow) **están sobreestimados**. Ver `docs/FIX-EDA-MODELADO-NIVEL1.md`.

Registra el resultado de `notebooks/08_nivel1_demanda.ipynb` (evaluación
walk-forward) y `notebooks/exportar_modelos_nivel1.py` (entrenamiento
final sobre el 100% del histórico + serialización), consumiendo
`matriz_as_of.parquet` de INV-15. No incluye el endpoint de predicción
que consumiría estos modelos desde la API — HU aparte, pendiente.

## 1. Enfoque: dos modelos por rama, tres ramas

Por cada rama se entrenan dos modelos, no uno:

- **modelo q50** (`alpha=0.5`): el que se compara contra el piso por
  WAPE — mide capacidad predictiva pura.
- **modelo q_negocio** (`alpha` de la función de costo, sección 2): el
  que saldría a producción. Se evalúa con *pinball loss* y cobertura
  empírica, no con WAPE.

Tres ramas, resultado de 3 rondas de búsqueda registradas en MLflow (ver
`ventas2/docs/INV-62-inventario-real.md` e `INV-63-correccion-factor-calendario.md`
para el detalle de cada ronda):

| Rama | Tipo de modelo | Config |
|---|---|---|
| `intermitente` (71.1% del conjunto, grano diario) | LightGBM cuantílico | 434 árboles, 78 hojas, afinado por búsqueda bayesiana |
| `suave_no_perecedero` | Ensamble Tweedie + LightGBM | `w_tweedie=0.5` |
| `suave_perecedero` | Ensamble Tweedie + LightGBM | `w_tweedie=0.6` |

Croston/SBA se probó de verdad para `intermitente` (no solo mencionado)
y perdió contra la media móvil — hallazgo negativo documentado, no
oculto: esa rama se atiende con LightGBM, no con un método de
intermitencia clásico.

## 2. Cuantil de negocio: costos

```
no_perecedero: Cu=0.25, Co=0.03  -> alpha_negocio = 0.893
perecedero:    Cu=0.20, Co=1.00  -> alpha_negocio = 0.167
```

Estos costos **están validados por el negocio** (confirmado por el usuario el 2026-09-24). El rótulo `SUPUESTO -- pendiente de
validar` que aún aparece en el código de 08, en `exportar_modelos_nivel1.py` y en `models/nivel1_metadata.json` quedó
desactualizado. Aun así el cuantil es muy sensible a `Co` (bajarlo de 1.00 a 0.25 movería el cuantil de perecederos de 0.17 a
0.44), por lo que se pueden variar como análisis de sensibilidad (ejercicio de modelado, no requerimiento de negocio).

## 3. Resultado de la validación walk-forward (con purge, folds 2 a 5)

Corrida del 2026-09-24, con 2022 en el DW (matriz de 262.429 filas) y entrenamiento purgado. **Los hiperparámetros y pesos de
ensamble NO se volvieron a buscar**: son los de la ronda anterior. `suave_perecedero` en el fold 2 queda con 168 filas de
entrenamiento tras el purge (< 200, el mínimo que 08 ya exigía), así que esa rama se evalúa **solo en los folds 3-5 (1.044 filas)**.

Mejora sobre la media móvil con IC95 (bootstrap de productos, `09_evaluacion_robusta`):

| Rama | WAPE q50 | Piso (media móvil) | Mejora vs. piso (IC95) | Cobertura empírica (objetivo) |
|---|---|---|---|---|
| intermitente | 0.433 | 0.438 | +1.2% [−6.1%, +5.6%] — **no distinguible del piso** | 0.886 (0.893) |
| suave_no_perecedero | 0.188 | 0.190 | +1.0% [−3.8%, +4.9%] — no distinguible | 0.907 (0.893) |
| suave_perecedero | 0.141 | 0.137 | −2.5% [−23.6%, +2.0%] — no supera | 0.178 (0.167), pero por fold 0.27 / 0.08 / 0.23 |

(WAPE agrupado por filas; la agregación de la notebook 08 da 0.431 / 0.188 / 0.141.) En `intermitente`, **sin el producto P1632
(Huevos) la mejora es +4.9%, IC95 [+4.0%, +5.7%]**: un solo producto de altísimo volumen diluye una mejora real en el resto.

Comparación con lo que se reportaba antes del purge: `intermitente` 0.427 → 0.433 (mejora +2.1% → +1.2%), `suave_no_perecedero`
0.193 → 0.188 (pasa de −1.6% a +1.0%, ambos sin distinción del piso), `suave_perecedero` 0.143 → 0.141 (pero ahora sobre 3 folds y
con peor mejora: −4.2% → −2.5% en sus propios folds; no comparables).

Por fold (WAPE q50 del modelo vs. media móvil):

| Fold | intermitente | suave_no_perecedero | suave_perecedero |
|---|---|---|---|
| 2 | 0.449 vs. 0.408 (pierde) | 0.188 vs. 0.180 (pierde) | omitido (train < 200) |
| 3 | 0.466 vs. 0.490 | 0.233 vs. 0.218 (pierde) | 0.158 vs. 0.140 (pierde) |
| 4 | 0.422 vs. 0.451 | 0.186 vs. 0.187 (empate) | 0.158 vs. 0.150 (pierde) |
| 5 | 0.410 vs. 0.435 | 0.166 vs. 0.193 | 0.118 vs. 0.125 |

La cobertura agrupada de `suave_perecedero` (0.178) parece cercana al objetivo (0.167), pero es el promedio de folds muy
dispares (0.27, 0.08, 0.23): el cuantil de esa rama **no está calibrado** y no debe usarse para la alerta de producción.

Estos resultados incluyen la corrección del bug de calendario (`factor_calendario_ventana`, ver `INV-15-feature-engineering.md`).

### Recalibración conformal (split-CQR)

`CONFORMAL_QNEG_RAMAS = {'suave_no_perecedero', 'suave_perecedero'}` — ambas ramas suaves reciben la corrección, y la separación
fit/calib ahora también se purga (la ventana objetivo de las filas de fit no toca el periodo de calib). `intermitente` queda sin
corregir porque ya está calibrada.

## 4. Validación de generalización — caveats honestos

Recorte sin el fold 5 (agrupando el error absoluto de las filas de `evaluacion_nivel_1.parquet`):

| Rama | Con fold 5 (modelo vs. piso) | Sin fold 5 (modelo vs. piso) |
|---|---|---|
| intermitente | 0.433 vs. 0.438 (+1.2%) | 0.443 vs. 0.439 (−0.8%) |
| suave_no_perecedero | 0.188 vs. 0.190 (+1.0%) | 0.196 vs. 0.189 (−3.6%) |
| suave_perecedero | 0.141 vs. 0.137 (−2.5%) | 0.158 vs. 0.146 (−7.9%) |

- **`intermitente`**: gana al piso en los folds 3, 4 y 5 (con IC95 > 0 en cada uno por separado) y pierde el fold 2, donde P1632
  aporta un exceso de error (25.100) mayor que el exceso neto del fold (21.472). **Sin el fold 5 ya no gana** (−0.8%): el resultado
  agrupado no es robusto.
- **`suave_no_perecedero`**: solo gana en el fold 5 (+14.4%, IC95 justo en 0); pierde los folds 2 y 3. Sin el fold 5, −3.6%.
- **`suave_perecedero`**: pierde en los folds 3 y 4 y gana por poco en el 5 (0.118 vs. 0.125, con IC95 muy ancho); sin el fold 5, −7.9%.
- El origen `semana_santa` cae en el fold 1, que solo entrena: **el modelo nunca se evalúa en Semana Santa**, pese a que INV-14 §8
  pide incluirla.
- La verificación con semilla alternativa (123 vs. 42) de una ronda anterior no se repitió con el protocolo corregido.
- **Limitación explícita**: no es una validación con un corte de folds completamente distinto (requeriría reconstruir
  `matriz_as_of.parquet` con fronteras nuevas). El fold 5 tampoco es un holdout virgen: las rondas 1-5 de búsqueda lo usaron.

> **Actualización posterior (fix del EDA):** `docs/FIX-EDA-MODELADO-NIVEL1.md` mide estas diferencias con IC95 y prueba otros
> horizontes y modelos relativos al nivel. Con el protocolo corregido: la mejora de `intermitente` no se distingue del piso, se diluye
> por un solo producto (P1632), y un modelo relativo al nivel (`rel`) la lleva a ~+5.1% con IC95 > 0; `suave_no_perecedero` no supera
> el piso a 15 días pero sí a 7. Los `models/*.joblib` de este documento siguen siendo la variante baseline.

## 5. Intentos que NO funcionaron (documentados para no repetirlos)

- **Modelo hurdle** (clasificador de cero + regresión sobre positivos)
  para `suave_perecedero`: descartado, premisa falsa — esa rama no
  tiene NINGUNA fila con `target_demanda_15d == 0` en entrenamiento (es
  una suma de 15 días).
- **Transformación log1p/expm1**: disparó el WAPE a 7.1 (50x peor que
  el piso) — el target tiene skew=5.4, un error chico en escala log se
  vuelve enorme al invertir con `expm1` sin corrección de smearing de
  Duan.

## 6. Exportación a producción (`notebooks/exportar_modelos_nivel1.py`, v1)

> **Los `models/*.joblib` versionados ya no son esta variante.** Tras la fase E del fix del EDA, `notebooks/exportar_modelos_nivel1_v2.py` exporta:
> `intermitente` como cuantil LightGBM sobre el target relativo (tipo `relativo`, hiperparámetros vigentes, con recalibración conformal por estrato) y las ramas suaves como `baseline_cuantil`
> (media móvil y cuantil empírico de la razón por estrato de volumen, sin modelo entrenado). Esta sección describe el exportador v1, que sigue disponible
> para regenerar la variante baseline; ver `docs/FIX-EDA-MODELADO-NIVEL1.md`.

Reentrena la misma configuración de cada rama (`MODELOS_POR_RAMA`,
copiada literal de `08_nivel1_demanda.ipynb`) sobre el **100% del
histórico disponible** — no walk-forward, porque el objetivo acá no es
medir desempeño (ya se midió arriba) sino producir el mejor modelo
posible para producción. El offset conformal también se recalcula sobre
el 100% del histórico (split cronológico 80/20 fit/calib, con purge de la ventana objetivo entre fit y calib).

| Rama | Filas de entrenamiento final | Offset conformal (q_negocio) |
|---|---|---|
| intermitente | 257.894 | N/A (no necesita corrección) |
| suave_no_perecedero | 2.735 | +6.43 |
| suave_perecedero | 1.800 | +2.05 |

(Reentrenados el 2026-09-24, tras la corrección del purge, sobre la matriz con 2022. `nivel1_metadata.json`
lleva la huella `8f2d656df51a` de `matriz_as_of.parquet` y las métricas
walk-forward de la sección 3 como referencia. En esta corrida el tracking
server respondió en `http://127.0.0.1:5000`, experimento 13.)

Artefactos generados:

- `models/nivel1_<rama>.joblib` (3 archivos) — cada uno un diccionario
  con el/los modelo(s) entrenado(s), el peso de ensamble si aplica, el
  factor empírico de Tweedie para el cuantil de negocio, y el offset
  conformal (o `None`).
- `models/nivel1_metadata.json` — features, supuestos de costo,
  `alpha_negocio` por rama, huella SHA-256 de `matriz_as_of.parquet`, y
  las métricas de la validación walk-forward de la sección 3 (citadas
  como referencia, **no** como desempeño del modelo exportado, que no
  tiene conjunto de test propio por entrenarse sobre el 100% del dato).
- 3 runs en MLflow, experimento `INV-17-inventaio-modelos-produccion`
  (mismo tracking server compartido con `ventas2`,
  `http://172.16.0.147:5000`) — params (`alpha_negocio`, offset
  conformal, filas de entrenamiento), métricas de referencia
  (`walkforward_*`), y el `.joblib` como artefacto.

Verificado que los 3 `.joblib` cargan con `joblib.load()` y predicen
sobre una fila de ejemplo sin error.

## Features usadas (14, ver `docs/INV-15-feature-engineering.md` §7 para el catálogo completo)

`trail_15`, `trail_15_prev`, `nivel_medio_60d`, `dias_desde_ultima_venta`,
`frecuencia_as_of`, `adi_as_of`, `cv2_as_of`, `racha_max_as_of`,
`factor_calendario_ventana`, `cond1_espacio_bodega`, `cond2_perecedero`,
`cond3_refrigerado`, `cond4_papel_higienico`, `cond5_temporada`.

## Pendiente / fuera de alcance de esta HU

1. Actualizar el rótulo `SUPUESTO` de los costos en 08, en el exportador y en `nivel1_metadata.json` (los costos están
   validados, sección 2) y, si se quiere, correr un análisis de sensibilidad de `Cu`/`Co`.
2. **`suave_perecedero` no está lista para la alerta de negocio en producción** — no supera el piso y su cobertura por fold
   (0.27 / 0.08 / 0.23) muestra que el cuantil no está calibrado.
3. **Las dos ramas suaves no superan el piso a 15 días con el protocolo corregido** (`suave_no_perecedero` +1.0%, IC [−3.8%, +4.9%]).
   Los modelos exportados de esas ramas no ganan hoy a una media móvil; decidir si se sirven igual o si se atienden con la media móvil.
3b. **`intermitente` no se distingue del piso con IC95** (+1.2%; +4.9% sin P1632). Hiperparámetros y pesos siguen siendo los de la
   ronda anterior, afinados sin purge; no se re-buscaron.
4. **Endpoint de predicción en `api/`** que cargue estos `.joblib` y
   sirva pronósticos — HU aparte, no implementada acá.
5. Reconciliación jerárquica entre las dos ramas suaves y un corte de
   folds completamente nuevo — mencionados como trabajo futuro posible,
   no implementados. (2022, sin noviembre-diciembre, ya está agregado.)
6. Nivel 2 (clasificador de riesgo de quiebre): no entrenado — el
   inventario real de una sola fecha no alcanza la densidad temporal
   necesaria (`docs/INV-15-feature-engineering.md` §1). Queda como
   regla determinística sobre el pronóstico de Nivel 1.
