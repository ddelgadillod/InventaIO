# INV-17 — Modelo baseline de Nivel 1 (pronóstico de demanda)

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

## 2. Cuantil de negocio: costos declarados como supuestos

```
no_perecedero: Cu=0.25, Co=0.03  -> alpha_negocio = 0.893
perecedero:    Cu=0.20, Co=1.00  -> alpha_negocio = 0.167
```

**Sin fuente validada por el negocio** — quedan declarados como
supuestos explícitos, no como resultado. `Co=1.00` para perecederos
asume merma total dentro de los 15 días; solo es defendible para
productos que caducan en esa ventana (fruta fresca), no para lácteos o
embutidos. El cuantil resultante (0.167) es muy sensible a este
supuesto: bajarlo a `Co=0.25` movería el cuantil de 0.17 a 0.44.

## 3. Resultado de la validación walk-forward (5 folds expansivos)

| Rama | WAPE q50 | Piso interno (media móvil) | ¿Supera el piso? | Cobertura empírica (objetivo) |
|---|---|---|---|---|
| intermitente | **0.416** | 0.430 | **Sí** (+3.3%) | 0.891 (0.893) — calibrado |
| suave_no_perecedero | **0.182** | 0.190 | **Sí** (+4.2%) | 0.919 (0.893) — con recalibración conformal |
| suave_perecedero | **0.150** | 0.137 | No (−9.5%, brecha reducida) | 0.115 (0.167) — mejoró con conformal, sigue sin calibrar del todo |

Estos son los números finales tras la corrección del bug de calendario
(`factor_calendario_ventana`, antes solo usaba 3 de 11 eventos
confirmados — ver `INV-15-feature-engineering.md`) y la re-búsqueda de
hiperparámetros sobre la matriz ya corregida.

### Recalibración conformal (split-CQR)

`CONFORMAL_QNEG_RAMAS = {'suave_no_perecedero', 'suave_perecedero'}` —
ambas ramas suaves necesitan la corrección (con el peso de ensamble
final, `suave_no_perecedero` sin corrección tenía desvío 0.088; antes
de la re-búsqueda no la necesitaba). `intermitente` queda sin corregir
porque ya está calibrada — aplicar conformal donde no hace falta solo
agrega ruido.

## 4. Validación de generalización — caveats honestos

- **`intermitente`**: gana al piso en 3 de 4 folds y **sigue ganando
  incluso excluyendo el fold 5** (+1.3% sin él) — resultado
  razonablemente robusto.
- **`suave_no_perecedero`**: sin el fold 5, el resultado pasa a ser un
  **empate técnico** (+0.3%/−0.6% según la ronda), no una pérdida clara
  pero tampoco una victoria confirmada — no reportar como "supera el
  piso" sin esta salvedad.
- **`suave_perecedero`**: pierde consistentemente, con o sin fold 5.
- Semilla alternativa (123 vs. 42): diferencia < 0.002 en `wape_q50` en
  las 3 ramas — el resultado no es sensible a la aleatoriedad del
  entrenamiento; la fragilidad de `suave_no_perecedero` es temporal (qué
  folds entran), no de inicialización.
- **Limitación explícita**: esto NO es una validación cruzada con un
  corte de folds completamente distinto — requeriría reconstruir
  `matriz_as_of.parquet` con fronteras de fold nuevas (INV-15). Es la
  aproximación más rigurosa posible sin rehacer esa etapa.

## 5. Intentos que NO funcionaron (documentados para no repetirlos)

- **Modelo hurdle** (clasificador de cero + regresión sobre positivos)
  para `suave_perecedero`: descartado, premisa falsa — esa rama no
  tiene NINGUNA fila con `target_demanda_15d == 0` en entrenamiento (es
  una suma de 15 días).
- **Transformación log1p/expm1**: disparó el WAPE a 7.1 (50x peor que
  el piso) — el target tiene skew=5.4, un error chico en escala log se
  vuelve enorme al invertir con `expm1` sin corrección de smearing de
  Duan.

## 6. Exportación a producción (`notebooks/exportar_modelos_nivel1.py`)

Reentrena la misma configuración de cada rama (`MODELOS_POR_RAMA`,
copiada literal de `08_nivel1_demanda.ipynb`) sobre el **100% del
histórico disponible** — no walk-forward, porque el objetivo acá no es
medir desempeño (ya se midió arriba) sino producir el mejor modelo
posible para producción. El offset conformal también se recalcula sobre
el 100% del histórico (split cronológico 80/20 fit/calib).

| Rama | Filas de entrenamiento final | Offset conformal (q_negocio) |
|---|---|---|
| intermitente | 224.261 | N/A (no necesita corrección) |
| suave_no_perecedero | 2.834 | +4.19 |
| suave_perecedero | 1.728 | +1.98 |

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

1. **Validar los costos con el negocio** (sección 2) — mientras sean
   supuestos, el cuantil de la rama perecedera debe reportarse como
   rango, no como valor único.
2. **`suave_perecedero` no está lista para la alerta de negocio en
   producción** — no supera el piso y su calibración, aunque mejoró,
   sigue sin llegar al objetivo.
3. **`suave_no_perecedero` "supera el piso" no está confirmado de forma
   robusta** — depende del fold 5, ver sección 4.
4. **Endpoint de predicción en `api/`** que cargue estos `.joblib` y
   sirva pronósticos — HU aparte, no implementada acá.
5. Reconciliación jerárquica entre las dos ramas suaves, un corte de
   folds completamente nuevo, y agregar 2022 (sin noviembre-diciembre)
   — todo mencionado como trabajo futuro posible, no implementado.
6. Nivel 2 (clasificador de riesgo de quiebre): no entrenado — el
   inventario real de una sola fecha no alcanza la densidad temporal
   necesaria (`docs/INV-15-feature-engineering.md` §1). Queda como
   regla determinística sobre el pronóstico de Nivel 1.
