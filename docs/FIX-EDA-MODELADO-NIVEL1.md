# Fix EDA / modelado de Nivel 1 (rama `fix/eda-modelado-nivel1`)

Continuación de `INV-17-modelo-baseline.md` tras la re-ejecución con datos de 2022. Objetivo: saber si las diferencias contra el
piso (media móvil) son reales, si más features o modelos ayudan y qué pasa a otros horizontes. Todo se mide con el arnés
`notebooks/evaluar_nivel1.py` (IC95 por bootstrap de productos) y se registra en MLflow (`http://127.0.0.1:5000`).

## Corrección del purge (leer primero)

La primera versión de este trabajo (commit `e1ba5b2`, no publicado) tenía un error de evaluación heredado de 07/08: el modelo de
cada fold entrenaba con **todas** las filas de folds anteriores, pero los folds de prueba son adyacentes y la ventana objetivo dura
15 días hábiles. Las últimas filas de entrenamiento tenían como etiqueta demanda que ocurre **dentro del periodo de prueba**
(20% del entrenamiento del fold 2, 3-6% en los demás), lo que inflaba el desempeño del modelo frente al piso.

Corrección: `purgar_entrenamiento` (en `common_priorizacion.py`) descarta esas filas; se aplica en 08, en la separación fit/calib
de la recalibración conformal (08 y exportador) y en todos los notebooks nuevos. Las combinaciones rama × fold que quedan con
menos de 200 filas de entrenamiento se omiten (regla que 08 ya tenía): `suave_perecedero` en el fold 2 (168 filas) deja de
evaluarse, así que esa rama se mide en los folds 3-5. Se re-ejecutó toda la cadena (08 → 09 → 07c → 11 → 10) y se reentrenaron los
modelos; los runs de MLflow anteriores quedaron con la etiqueta `protocolo=sin_purge_obsoleto` y los nuevos con `con_purge`.

Efecto (h=15, mejora sobre el piso), medido antes de re-ejecutar la cadena:

| Rama | Modelo | Sin purge | Con purge |
|---|---|---|---|
| intermitente | `rel_w` | +5.7% [+5.0, +6.4] | +3.6% [+0.8, +5.4] |
| suave_no_perecedero | `rel_w` | +6.2% [+2.6, +10.7] | +2.3% [−1.6, +7.0] |
| suave_perecedero | `rel_w` | −5.5% | −10.0% |

Consecuencia: **las rondas de búsqueda INV-62/63 (383 corridas) también se evaluaron sin purge**, así que los hiperparámetros y
pesos de ensamble vigentes se eligieron con un criterio inflado. No se repitieron.

## Cadena de notebooks

```
07 (parametrizado, HORIZONTE_07=15 por defecto; también 7 y 30)
 ├─► 07b_features_extendidas ─► matriz_as_of_v2.parquet ─► 07c_ablacion_features        (fase B)
 ├─► 08 (baseline, con purge) ─► 09_evaluacion_robusta ─► decision_09.json               (fase A)
 ├─► 11_modelos_relativos ─► decision_11.json                                             (fase D)
 ├─► matriz_as_of_h7 / h30 ─► 10_horizontes ─► decision_10.json                           (fase C)
 └─► 12_segmentacion_volumen ─► 13_cuantiles_y_costos ─► decision_12.json, decision_13.json (fase E)
                                   ├─► 14_calibracion_conformal_estrato ─► decision_14.json
                                   └─► 15_busqueda_hparams_relativo ─► decision_15.json
                                        └─► exportar_modelos_nivel1_v2.py ─► models/*.joblib + ml_service
```

- `07`: el horizonte se lee de `HORIZONTE_07`. Con `15` la matriz sale **idéntica byte a byte** (huella `8f2d656df51a`); con otro
  `h` escribe `matriz_as_of_h{H}.parquet` sin pisar nada.
- `evaluar_nivel1.py`: bootstrap de productos, leave-one-fold-out, concentración del error, política de holdout, `registrar_mlflow`.
- `modelos_nivel1.py`: variantes `v1`, `rel_w`, `rel`, `res_mm` parametrizadas por horizonte, con la configuración `MODELOS_POR_RAMA`
  de 08 y sin búsqueda de hiperparámetros.
- Cada notebook verifica la huella del anterior, escribe la suya y una decisión mecánica (`decision_*.json`); en 07c, 10 y 11
  `v1` reproduce 08 exactamente (diferencia máxima 0.000).

| Experimento MLflow | Notebook | Runs (`con_purge`) |
|---|---|---|
| `EDA-fix-nivel1-09-evaluacion-robusta` | 09 | 3 |
| `EDA-fix-nivel1-07b-features-extendidas` | 07b | 1 (no afectado por el purge) |
| `EDA-fix-nivel1-07c-ablacion-features` | 07c | 18 |
| `EDA-fix-nivel1-11-modelos-relativos` | 11 | 15 |
| `EDA-fix-nivel1-10-horizontes` | 10 | 18 |
| `EDA-fix-nivel1-12-segmentacion-volumen` | 12 | 32 |
| `EDA-fix-nivel1-13-cuantiles-y-costos` | 13 | 28 |
| `EDA-fix-nivel1-14-calibracion-conformal-estrato` | 14 | 20 |
| `EDA-fix-nivel1-15-busqueda-hparams-relativo` | 15 | 31 (30 trials + confirmación) |
| `INV-17-inventaio-modelos-produccion-v2` | exportador v2 | 3 |

## Fase A — ¿las mejoras contra el piso son reales? (09)

IC 95% por bootstrap de productos (2.000 remuestreos), modelo q50 vs. media móvil, sobre `evaluacion_nivel_1.parquet` de 08:

| Rama | Mejora vs. piso | IC95 | ¿Supera con IC? |
|---|---|---|---|
| intermitente | +1.2% | [−6.1%, +5.6%] | No |
| suave_no_perecedero | +1.0% | [−3.8%, +4.9%] | No |
| suave_perecedero (folds 3-5) | −2.5% | [−23.6%, +2.0%] | No |

1. **La ventaja de `intermitente` no se distingue del piso, pero un solo producto la diluye.** Sin **P1632 (Huevos)** la mejora es
   **+4.9%, IC95 [+4.0%, +5.7%]**. En el fold 2 su exceso de error (25.100) supera el exceso neto de todo el fold (21.472). Los folds
   3, 4 y 5 tomados por separado ganan con IC95 > 0; el fold 2 pierde.
2. **P1632 concentra el volumen**: es ~14.7% del volumen de prueba (los 10 mayores productos, 28.7%; los 500 mayores, 78.8%) y 182 de
   6.427 pares mueven la mitad del volumen (medido sin purge, es una descripción del dato).
3. **Dónde falla**: en una serie concreta (P1632 en PRINCIPAL, demanda de ~2.600 a ~3.500 por ventana). El modelo predice ~560 mientras
   la media móvil da ~2.600-3.000 (medido antes del purge). No es extrapolación fuera de rango (`trail_15` nunca supera el máximo de entrenamiento): es una zona
   con muy pocas filas de entrenamiento (p99.9 de `trail_15` = 336).
4. Sin el fold 5 el agregado de `intermitente` ya no gana (−0.8%) y `suave_no_perecedero` cae a −3.6%.

## Fase B — ¿más features ayudan? (07b, 07c)

11 features nuevas as-of (`trail_7`, `trail_28`, `ewma_14`, `ewma_28`, `dias_con_venta_15`, `ratio_trail_nivel`, `cat_ratio`,
`share_cat`, `suc_ratio`, `n_festivos_ventana`, `n_inicio_mes_ventana`), con prueba de no-fuga (recalcular con la rejilla truncada en
`t`: diferencia 0.0). Un primer intento dejó `cat_ratio` con valores de hasta 2.000.000 (división por 0); se suavizó con
`(g_t+1)/(g_prev+1)` y se agregó un assert de escala.

Ablación con hiperparámetros fijos. Regla pre-registrada: se elige la configuración con mejor mejora sobre `v1` en los folds 2-4 y se
adopta solo si su IC95 ahí es > 0 **y** el fold 5 no la contradice.

| Rama | Mejor config (folds 2-4) | vs. v1 en 2-4 (IC95) | Fold 5 | ¿Adopta? |
|---|---|---|---|---|
| intermitente | v1+memoria | +0.4% [+0.2%, +0.8%] | +0.3% | **Sí (efecto mínimo)** |
| suave_no_perecedero | v1+momentum | +0.1% [−1.2%, +2.0%] | −3.2% | No |
| suave_perecedero | v1+momentum | +2.4% [−0.2%, +14.3%] | −2.3% | No |

En `intermitente` el grupo `memoria` (`trail_7`, `trail_28`, `ewma_14`, `ewma_28`, `dias_con_venta_15`) pasa la regla, pero la mejora es de
0.4 puntos porcentuales: estadísticamente distinguible de cero y prácticamente irrelevante (contra el piso, +1.6% frente a +1.2% de `v1`).
Las demás configuraciones y ramas no aportan. Las 14 features actuales capturan casi todo lo que estas 11 podían aportar.

## Fase D — modelos relativos al nivel (11)

Con las 14 features v1 y los mismos hiperparámetros, se cambia solo la forma del target (`base = nivel_medio_60d · H + 1`): `rel_w`
(aprende `y/base` con peso `base`, equivale al mismo L1 en unidades originales), `rel` (`y/base` sin pesos), `res_mm` (`y − media_movil`)
y `mezcla50` (0.5·v1 + 0.5·media móvil, sin entrenar). Mejora vs. piso con IC95, todos los folds:

| Rama | v1 | rel_w | rel | res_mm | mezcla50 |
|---|---|---|---|---|---|
| intermitente | +1.2% [−6.1, +5.6] | +3.6% [+0.8, +5.4] | **+5.1% [+4.5, +5.8]** | +4.6% [+4.2, +5.0] | +3.1% [+0.4, +4.8] |
| suave_no_perecedero | +1.0% [−3.8, +4.9] | +2.2% [−1.8, +7.0] | +2.3% [−1.3, +6.5] | +0.1% [−5.8, +4.4] | **+4.1% [+1.5, +6.1]** |
| suave_perecedero | −2.5% [−23.6, +2.0] | −8.0% [−11.3, +1.9] | −14.7% [−20.0, −1.1] | −10.9% [−28.4, −7.5] | +1.2% [−5.7, +2.7] |

Sobre P1632 (WAPE en PRINCIPAL, folds 2-5; piso 0.190): `v1` 0.419 → `rel` 0.176, `rel_w` 0.264, `res_mm` 0.190, `mezcla50` 0.270.
La hipótesis se sostiene, aunque `rel_w` corrige menos que antes del purge y `rel` (sin pesos) es la mejor variante en `intermitente`.

Decisión por la regla pre-registrada:

- **intermitente: la regla NO adopta** (mejor `rel`: +5.3% sobre v1 en 2-4, IC [−0.1%, +13.5%]; fold 5 +0.9%): el IC contra `v1` cruza 0 por
  una décima. Aun así `rel` **supera el piso con IC95 > 0** (+5.1% [+4.5, +5.8]) y `v1` no. Sin el peor producto de cada variante el
  resultado es casi igual (+4.9% para `v1`, +5.2% para `rel`): la ganancia es corregir series de altísimo volumen. Adoptarla es criterio, no regla.
- **suave_no_perecedero: la regla NO adopta** (mejor `mezcla50`: +5.5% sobre v1 en 2-4, IC [+2.9, +8.2], pero el fold 5 la contradice, −5.0%).
  `mezcla50` supera el piso con IC (+4.1% [+1.5, +6.1]), pero es sobre todo contraer la predicción hacia el piso, no una mejora de modelado.
  Los modelos relativos no superan el piso en esta rama a 15 días.
- **suave_perecedero: la regla "adopta" `mezcla50`, pero no es una mejora de modelado**: +1.2% sobre el piso, IC [−5.7, +2.7]. Es mejor que
  `v1` solo porque `v1` perdía contra el piso. Las variantes relativas empeoran.

## Fase C — otros horizontes (10)

`07` con `HORIZONTE_07=7` y `30` (`matriz_as_of_h7/h30.parquet`; con `15` sigue idéntica). El WAPE absoluto no es comparable entre horizontes;
se compara la mejora sobre el piso de cada horizonte. Hiperparámetros afinados a 15 días, sin búsqueda. A h=15, `v1` reproduce 08 y `rel_w`
reproduce la fase D (diferencia máxima 0.000).

| Rama | h | Filas eval. | v1 vs. piso (IC95) | rel_w vs. piso (IC95) |
|---|---|---|---|---|
| intermitente | 7 | 484.234 | +4.7% [+0.2, +7.8] | **+7.5% [+6.9, +8.2]** |
| intermitente | 15 | 232.704 | +1.2% [−6.1, +5.6] | **+3.6% [+0.8, +5.4]** |
| intermitente | 30 | 121.860 | −2.1% [−14.8, +5.7] | **+4.3% [+2.9, +5.7]** |
| suave_no_perecedero | 7 | 4.981 | **+6.3% [+1.6, +10.8]** | **+10.0% [+6.3, +15.0]** |
| suave_no_perecedero | 15 | 2.410 | +1.0% [−3.8, +4.9] | +2.2% [−1.8, +7.0] |
| suave_no_perecedero | 30 | 801 | −4.4% [−9.8, +0.8] | +0.1% [−4.3, +4.3] |
| suave_perecedero | 7 | 3.294 | −4.2% [−14.6, −2.3] | −2.1% [−3.4, +1.1] |
| suave_perecedero | 15 | 1.044 | −2.5% [−23.6, +2.0] | −8.0% [−11.3, +1.9] |
| suave_perecedero | 30 | 542 | −25.5% [−80.4, −15.3] | −14.4% [−20.6, +1.7] |

- **La ventaja sobre el piso es mayor a horizontes cortos**: a 7 días `suave_no_perecedero` supera el piso con IC95 > 0 incluso con `v1`
  (+6.3%), y con `rel_w` +10.0%. A 15 y 30 días esa rama no lo supera.
- **`intermitente`**: `rel_w` supera el piso con IC95 > 0 en los tres horizontes; `v1` solo a 7 días.
- **`suave_perecedero`** no supera el piso en ningún horizonte.
- Por la regla de adopción sobre `v1` (folds 2-4 + fold 5), solo `suave_no_perecedero` a h=7 la cumple (+3.7% en 2-4, IC [+1.2, +7.2]; fold 5
  +4.4%). En `intermitente` el IC pareado contra `v1` cruza 0 en los tres horizontes.
- No se evaluó el horizonte natural `lead_time + revisión` por proveedor: no verifiqué si `lead_time_dias` es dato real o supuesto.
- Son 9 comparaciones (3 horizontes × 3 ramas) sin corrección formal por comparaciones múltiples.

## Fase E — segmentación por volumen y cuantiles (12, 13)

### Estratos (12)

Definidos **as-of** por fold: volumen de los últimos 365 días hábiles hasta `train_end` (nunca el del periodo de prueba). Cabeza = pares que acumulan el 50%
del volumen, medio = el siguiente 30%, cola = el 20% restante. Resultado: **200-209 pares en la cabeza** por fold (~2% de los 11.135 pares), 1.164-1.214 en el medio
y ~9.750 en la cola. Fuera de muestra la cabeza cubre 45-51% del volumen de prueba, así que la definición es estable. **La cabeza no es homogénea ni estable**:
47% de sus filas son de demanda errática, 26% lumpy y solo 28% suave (el medio es 50% intermitente / 45% lumpy; la cola, 88% intermitente).

Candidatos por estrato (folds 2-5; mejora vs. piso, IC95). `seg_v1` / `seg_v2` = modelo relativo entrenado solo con las filas del estrato (14 / 25 features);
`mm_cal` = media móvil × factor de calendario; `ets` = Holt-Winters aditivo semanal por serie (55.093 ajustes, cabeza y medio):

| Candidato | Cabeza (WAPE piso 0.250) | Medio (0.403) | Cola (0.662) |
|---|---|---|---|
| v1 (actual) | −8.2% [−25.6, +3.4] | +4.2% [+3.4, +5.1] | +6.5% [+6.1, +6.9] |
| rel (global relativo, referencia) | +2.2% [−0.3, +5.1] | +4.0% [+3.4, +4.7] | +6.5% [+6.1, +6.8] |
| mm_cal | +2.9% [+1.7, +4.1] | +1.3% [+1.0, +1.6] | +0.5% [+0.4, +0.6] |
| ets (por serie) | −1.8% [−4.7, +1.5] | +0.2% [−0.8, +1.1] | — |
| seg_v1 | +1.7% [−0.9, +4.9] | +4.6% [+3.8, +5.6] | +6.7% [+6.3, +7.2] |
| seg_v2 | **+4.8% [+2.9, +6.9]** | **+5.0% [+4.1, +5.8]** | +6.8% [+6.4, +7.3] |

Decisión contra el modelo global relativo `rel` (folds 2-4 con IC95 > 0 y fold 5 no contradictorio):

- **cabeza: no adopta**. El mejor por la regla fue `mm_cal` (+3.6% [−0.3, +7.2]; fold 5 −6.9%). `seg_v2` es el único candidato con IC > 0 contra el piso y positivo en el fold 5
  (+3.9% vs. `rel`), pero contra `rel` da +2.2% [−0.3, +4.0]: no distinguible.
- **medio: adopta `seg_v2`** (+1.1% [+0.5, +1.8], fold 5 +0.6%): efecto real pero pequeño.
- **cola: no adopta** (`seg_v2` +0.7% [+0.5, +1.0], pero el fold 5 la contradice, −0.3%).
- **Política híbrida** (mejor candidato por estrato en folds 2-4: `mm_cal`, `seg_v2`, `seg_v2`): +5.0% vs. piso [+4.3, +5.5], **+0.7% vs. `rel` [−0.1, +1.7]**
  (folds 2-4 +1.8% [+0.5, +3.6]; fold 5 −2.1% [−3.2, −1.0]) → **la segmentación no mejora al modelo global relativo**. La regla escogió `mm_cal` para la cabeza por 0.003 de WAPE
  sobre `seg_v2` en los folds 2-4 y falla en el fold 5; que `seg_v2` habría sido más estable es una observación posterior al fold 5, no una decisión válida.
- **Los modelos por serie (ETS) no ayudan** y EWMA × calendario empeora (−6.8% en cabeza).

**¿Cambia el feature engineering por estrato?** Sí, según el alcance del modelo. En modelos **globales**, agregar las 11 features de 07b empeora la cabeza (`v2_completa` −2.6% vs.
`v1`, `contexto` −1.2%, ambos distinguibles de cero) y casi no mueve medio y cola (≤ 0.6%). Entrenados **solo con las filas del estrato**, las 25 features ayudan en la cabeza
(`seg_v2` vs. `seg_v1`: +3.2% [+1.1, +4.9]) y apenas en el medio (+0.3% [+0.0, +0.6]). Es coherente con que un modelo global está dominado por la cola; no se probó un diseño de features
específico para la cabeza.

### Cuantiles y sensibilidad de `Cu`/`Co` (13)

LightGBM cuantílico sobre el target relativo (features v1, hiperparámetros de cada rama, con purge), en una rejilla de alphas (0.1, 0.167, 0.25, 0.5, 0.75, 0.893, 0.95) y por estrato,
contra un cuantil base sin modelo: `(media_movil+1) · Q_alpha(y/(media_movil+1))`. **Una primera versión usaba una base por rama y mostraba mejoras de 24-32% a alphas bajos; era un artefacto**
(esa base es muy floja en la cabeza: cobertura 0.03 con objetivo 0.10). Las decisiones se toman contra la **base por estrato**.

Pérdida pinball vs. la base por estrato (IC95):

| alpha | Todos | Cabeza | Medio | Cola |
|---|---|---|---|---|
| 0.167 | +7.6% [+5.9, +9.5] | +4.0% [+0.3, +8.9] | +8.0% [+6.7, +9.5] | +11.1% [+10.4, +11.8] |
| 0.250 | +9.2% [+7.6, +10.7] | +3.3% [+0.2, +7.0] | +5.8% [+4.8, +6.9] | +17.6% [+16.9, +18.4] |
| 0.500 | +4.5% [+3.3, +5.4] | +1.2% [−1.8, +3.7] | +2.2% [+1.6, +2.8] | +9.5% [+9.1, +10.0] |
| 0.893 | +4.5% [+2.0, +7.7] | +0.5% [−7.6, +10.1] | +6.5% [+5.7, +7.3] | +6.3% [+5.9, +6.7] |
| 0.950 | +5.7% [+2.8, +9.0] | −2.7% [−13.1, +7.3] | +10.1% [+8.7, +11.4] | +9.4% [+8.8, +10.0] |

- **Calibración**: en la cabeza el modelo **subcubre** a alphas altos (cobertura 0.788 con objetivo 0.893 y 0.853 con 0.95; la base por estrato da 0.899 y 0.946): justo donde está el volumen, el
  cuantil de servicio no llega al nivel pedido. A alphas bajos en la cola la cobertura (~0.34-0.38) refleja la masa de ceros del target (`P(y=0)` = 0.34 en las filas de prueba de la cola), no calibración.
- **Con los costos reales por rama** (alpha 0.893 y Cu=0.25/Co=0.03; alpha 0.167 y Cu=0.20/Co=1.00), mejora del costo esperado del cuantil frente a la base por estrato:

| Rama | LightGBM relativo | Producción (`pred_q_negocio` de 08) |
|---|---|---|
| intermitente (todos) | **+6.9% [+5.4, +9.2]** (cabeza +7.8% [+1.8, +15.8]; medio +7.0%; cola +6.3%); cobertura 0.884 (cabeza 0.82) | +0.6% [−5.4, +4.8]; en la cabeza −15.2% [−32.8, −1.4] |
| suave_no_perecedero | −38.6% [−47.2, −25.4] (cobertura 0.71) | −4.4% [−13.4, +1.8] (cobertura 0.907) |
| suave_perecedero (folds 3-5) | −18.7% [−22.6, −7.9] | −39.0% [−56.2, +1.2] (cobertura pooled 0.178; por fold 0.27 / 0.08 / 0.23) |

  En `intermitente`, pasar a un cuantil sobre el target relativo reduce el costo frente al cuantil de producción en 6.4% (cabeza: +20.0%). Para las ramas suaves, **ni el cuantil de
  producción (ensamble + conformal) supera a la base simple** (media móvil × cuantil empírico de la razón, por estrato), que además está calibrada (cobertura 0.169 con objetivo 0.167 en
  `suave_perecedero`). El LightGBM relativo de este notebook no es el modelo de producción de las suaves y no debe leerse como su evaluación.
- **Sensibilidad a `Cu`/`Co`** (Cu ∈ {0.1, 0.2, 0.25, 0.4}, Co ∈ {0.03, 0.1, 0.25, 0.5, 1.0}; alpha óptimo `Cu/(Cu+Co)` aproximado al alpha más cercano de la rejilla, diferencia máxima 0.115):
  la mejora global va de +2.9% a +9.2% y es positiva en toda la rejilla; la ganancia es mayor con alphas bajos-medios (Co grande: 0.25-0.45) y en la cabeza desaparece cuando el costo de faltante domina
  (Co=0.03 → alpha 0.77-0.93: −2.7% a +0.5%), con cobertura del modelo en la cabeza de 0.67-0.85.

### Calibración conformal por estrato (14) y re-búsqueda de hiperparámetros (15)

**14.** Recalibración split-CQR del cuantil relativo de `intermitente` (alpha 0.893), con separación fit/calib purgada y un offset por estrato as-of. `sin_cal` reproduce el
notebook 13 exactamente. **Logra la cobertura nominal en cada estrato** (cabeza 0.895, medio 0.901, cola 0.906; sin calibrar: 0.820 / 0.863 / 0.892), pero el costo no mejora:
contra `sin_cal` da +0.06% en folds 2-4 (IC95 [−1.1%, +1.0%]) y −3.5% en el fold 5. Los offsets de la cabeza se estiman con pocas filas (138 a 980) y varían entre folds
(0.11 a 0.25). Una variante con un solo offset global da el mejor costo (+7.5% vs. la base por estrato, cabeza con cobertura 0.869), pero tampoco pasa la regla (+1.0% vs. `sin_cal`,
IC [−0.0%, +1.7%]; fold 5 −0.3%). **La regla no adopta la calibración**: entre `sin_cal`, `cal_global` y `cal_estrato` las diferencias de costo (≤ 1.5%) están dentro del ruido;
la elección es operativa (si se exige cobertura garantizada por estrato, `cal_estrato`).

**15.** Re-búsqueda con purge (Optuna TPE, 30 trials, objetivo: costo Cu=0.25/Co=0.03 en los folds 2-4; el primer trial es la configuración vigente). El mejor trial mejora +1.4% en 2-4
(optimista: es el objetivo de la búsqueda) pero en el fold 5, visto una sola vez, **empeora** el costo (−0.6%, IC [−1.3%, +0.1%]) y el WAPE del q50 (−0.6%, IC [−1.4%, −0.02%]).
Los 30 trials se mueven en un rango estrecho (0.03734 a 0.03832 de costo por unidad vendida): la superficie es plana y la mejora en los folds de búsqueda no generaliza.
**No se adopta; se mantienen los hiperparámetros vigentes.**

### Exportación v2 y `ml_service`

Con las decisiones del usuario sobre las recomendaciones de la fase E (2026-09-24), `notebooks/exportar_modelos_nivel1_v2.py` escribe `models/nivel1_<rama>.joblib` y `nivel1_metadata.json`:

| Rama | Tipo | Qué es |
|---|---|---|
| intermitente | `relativo` | LightGBM cuantílico sobre `y/base` (q50 y alpha 0.893), hiperparámetros vigentes, **con recalibración conformal por estrato** del cuantil de negocio. 257.894 filas |
| suave_no_perecedero | `baseline_cuantil` | q50 = media móvil; cuantil = `(media_movil+1) · Q_0.893(razon)` por estrato (cabeza 1.325, medio 1.349, cola sin filas → global 1.333) |
| suave_perecedero | `baseline_cuantil` | igual con `Q_0.167` (cabeza 0.799, medio 0.723, cola 0.654) |

**Calibración por estrato (decisión del usuario).** El exportador estima offsets conformales relativos con el 20% más reciente del historial (`fecha_origen` ≥ 2025-08-13, fit purgado): cabeza +0.041
(n=1.440), medio +0.059 (n=11.106), cola −0.014 (n=44.496), global −0.007; el cuantil de negocio pasa a `base · (q + offset_estrato)`. Efecto sobre el snapshot vigente de `intermitente`: el cuantil sube en promedio
+2.3% en la cabeza y +3.3% en el medio y baja −2.9% en la cola (P1632|PRINCIPAL: 4.254 → 4.373). Antes de exportar, el script verifica que el procedimiento reproduce los offsets del fold 5 de 14
(0.211 / 0.114 / 0.006). Esta calibración **no cumple la regla pre-registrada** (14: costo sin mejora con IC95 y peor en el fold 5) y se activa por decisión del usuario para garantizar cobertura por estrato;
`--sin-calibracion` la desactiva. **Cautela**: el offset de la cabeza varió mucho entre periodos (0.11 a 0.25 en los folds de 14; +0.041 con el 20% más reciente), así que no está comprobado que el modelo
exportado alcance 0.893 en la cabeza fuera de muestra; las ventas de 2026 permitirán medirlo con un holdout limpio.

Los estratos se definen a la fecha del último dato (2025-12-31: 218 pares en la cabeza, 1.270 en el medio, 9.647 en la cola) con `estratos_as_of` (`common_priorizacion.py`), verificada contra el
notebook 12 en los 4 folds. `ml_service/prediccion/motor.py` soporta los dos tipos nuevos, incluido el offset relativo por estrato, sin retirar los v1 (35 tests, todos pasan; comprobación puntual: P1632|PRINCIPAL da
q50=3.206 y cuantil de negocio 4.254 frente a una media móvil de 2.948, donde el modelo v1 predecía ~560). Los costos `Cu`/`Co` quedan rotulados como validados por el negocio.

## Limitaciones

- **El fold 5 no es un holdout virgen**: las rondas 1-5 de búsqueda lo usaron. Un holdout limpio requiere ventas posteriores a 2025-12-31.
- Las **rondas de búsqueda de hiperparámetros INV-62/63 se evaluaron sin purge**; los hiperparámetros vigentes no se re-buscaron.
- `suave_perecedero` se evalúa solo en los folds 3-5 (22 productos, 1.044 filas): sus IC son muy anchos.
- Quitar P1632 es una **sensibilidad post hoc**, no un desempeño citable; sirve para localizar el problema.
- Solo se evaluó el **q50** (WAPE). Los modelos relativos **no se han evaluado ni recalibrado para el cuantil de negocio**.
- Los `models/*.joblib` versionados siguen siendo la variante `v1` (reentrenada con 2022 y con la calibración conformal purgada); nada de las
  fases C y D se exportó. No se repitió la prueba de semilla alternativa.
- El bootstrap remuestrea productos; en las ramas suaves hay solo 22-60, lo que ensancha los IC. Comparaciones múltiples sin corrección
  formal (6 configuraciones en B, 5 variantes en D, 9 celdas en C, 11 candidatos × 3 estratos en E).
- Fase E: hiperparámetros fijos (los de la cabeza son de capacidad chica, elegidos a priori, no afinados); el ETS usa periodo 7 sobre la rejilla de días hábiles, que puede no coincidir exactamente con la semana
  calendario; el cuantil de la sección 13 es LightGBM relativo **sin recalibración conformal**, y la base usa solo filas de entrenamiento con purge; el `pred_q_negocio` de producción se evaluó tal como sale de 08. Los estratos
  se recalculan por fold con datos hasta `train_end`; en producción habría que decidir cada cuánto se recalculan.
- Los costos `Cu`/`Co` están validados por el negocio; en la sensibilidad se varían solo como ejercicio.

## Siguiente paso

1. Cuando lleguen las **ventas de 2026**: construir la matriz as-of con esos datos (07 y el ETL), medir con los modelos exportados la cobertura por estrato y el costo frente a la base (holdout limpio)
   y volver a estimar los offsets. Es la única forma de saber si la calibración de la cabeza (+0.041) es la adecuada o si hay que fijar una política de recalibración periódica.
   Los modelos y las reglas de decisión de esa evaluación quedaron **preregistrados** el 2026-09-25, antes de ver datos de 2026: `docs/PREREGISTRO-HOLDOUT-2026.md`
   (MLflow `EDA-fix-nivel1-16-holdout-2026`, run `preregistro_v1`).
2. Las ramas suaves se sirven con la base simple. Si se consiguen más datos (ventas 2026), reevaluar si un modelo las supera con IC95 y usar esas ventas como holdout limpio.
3. La cabeza merece un modelo propio si aparece evidencia distinguible (hoy `seg_v2` no se separa del global relativo con IC).
4. ~~Los tests de `ml_service` usan cotas de sanidad amplias; falta una prueba de regresión numérica contra las predicciones de los notebooks.~~ Resuelto en el fix de INV-20:
   `ml_service/tests/test_paridad_matriz.py` compara features y predicciones calculadas desde la bodega con `matriz_as_of.parquet` (idénticas en 3.325 filas).
5. Pendientes generales: ~~`features_snapshot.parquet` sigue siendo un paso manual~~ (el servicio ya lee la bodega, ver `docs/INV-20-ml-service.md`); el rótulo `SUPUESTO` sigue
   en el código del notebook 08 (los costos están validados).
