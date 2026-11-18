# INV-62 · Reentrenamiento programado de los modelos de pronóstico

**Fecha:** 18-nov-2026 · **Requerimientos:** `docs/INV-62-requerimientos.md` · **Protocolo de la receta:**
`notebooks/preregistro_receta_2026.json` (registrado antes de correr: commit `7ce78df`, run `preregistro_receta_v1` del experimento
`INV-62-reentrenamiento-nivel1`).

Los términos (origen, estrato, cuantil de negocio, cobertura, WAPE, intervalo de confianza del 95 %, purge) están definidos en
`docs/INV-63-requerimientos.md`. Los corchetes son el intervalo de confianza del 95 %, por bootstrap de productos.

## 1. Qué hace

Cada lunes a las 6:00, un temporizador de systemd de usuario en WSL corre `scripts/reentrenar.sh`:

1. **Arranca MLflow** si no corre. Si no responde, la corrida falla con código 2 y la unidad queda en «failed».
2. **Busca datos nuevos:** compara la fecha máxima y la huella de `fact_ventas.csv` con las de la última corrida terminada (las lee de
   MLflow). Si son iguales, registra «sin datos nuevos» y termina.
3. **Arma la matriz** con el catálogo vivo:
   - los pares de las sucursales modeladas cuyo producto está en el catálogo del DW;
   - orígenes cada 15 días hábiles;
   - estratos recalculados al corte;
   - la máscara de demanda censurada con la foto de inventario del DW.
4. **Aplica la regla de promoción.** En los últimos 12 orígenes, la receta se entrena en 3 cortes con purge y se compara con el modelo
   vigente sobre las mismas filas. Pasa si:
   - baja el costo con un intervalo por encima de 0;
   - no empeora el WAPE;
   - deja la cobertura a 0,05 o menos de 0,893 en la rama y en cada estrato con al menos 200 filas.
5. **Si pasa,** entrena el candidato con todos los datos y lo deja en una rama local `reentrenamiento/AAAAMMDD-HHMM` con `models/` y
   `SHA256SUMS` regenerados. Una persona hace el push y abre el PR; el CI comprueba las huellas.
6. **Si no pasa,** lo registra como «rechazado» y el vigente no cambia.

Cada corrida deja un run en MLflow (experimento `INV-62-reentrenamiento-nivel1`, etapa «corrida»). El run lleva la versión de los datos,
la receta, el estado (sin datos nuevos, rechazado, promovible o fallo) y las métricas de la regla por estrato. También queda un registro
en `~/.local/state/inventaio/reentrenamiento/` (se conservan los 12 últimos) y la salida en el journal.

## 2. Instalación, periodicidad y operación

```bash
# desde el repositorio (después de integrar, desde ~/InventaIO)
bash scripts/instalar_reentrenamiento.sh RUTA_DW        # instala y habilita el temporizador (lunes 6:00, Persistent=true)
systemctl --user list-timers inventaio-reentrenamiento.timer
systemctl --user start inventaio-reentrenamiento.service  # corrida inmediata, la misma que dispara el temporizador
systemctl --user status inventaio-reentrenamiento.service # «failed» si la corrida no terminó o MLflow no respondió
journalctl --user -u inventaio-reentrenamiento            # salida de las corridas
bash scripts/instalar_reentrenamiento.sh --quitar       # deshabilita y borra las unidades
```

- **Configuración** en `~/.config/inventaio/reentrenamiento.env`:
  - `REENTRENAMIENTO_DW`: el DW en CSV, la salida del ETL;
  - `REENTRENAMIENTO_REPO`: el repositorio con los modelos vigentes;
  - `REENTRENAMIENTO_BASE`: la rama base del candidato.
- **WSL apagado:** el temporizador corre solo con una sesión de WSL abierta, porque el usuario no tiene «linger». Con `Persistent=true`,
  la corrida pendiente se hace al volver a abrir WSL.
- **Datos nuevos:** la carga de los Excel de ventas sigue siendo manual (parser de ventas2, ETL con `ETL_SALIDA_DIR` y la foto que
  corresponda). Mientras no se cargue nada, el temporizador registra «sin datos nuevos».
- **Prueba del proceso de exportación:** `python notebooks/reentrenar_nivel1.py --dw … --repo … --exportar-sin-regla` exporta aunque el
  candidato no cumpla la regla. La rama es `reentrenamiento/prueba-…`, el estado es «prueba_exportacion» y la corrida no cuenta como la
  última. Nunca desde el temporizador.

## 3. Reversa al modelo anterior

Los modelos van dentro de la imagen del servicio de predicción, con sus huellas en `models/SHA256SUMS`.

- **En producción y staging:** revertir el commit del PR del candidato (`git revert -m 1 <merge>`) y desplegar la versión anterior
  (`scripts/desplegar_staging.sh --reversa` o el tag anterior).
- **En local:** `git checkout <commit-anterior> -- models/`, comprobar `cd models && sha256sum -c SHA256SUMS` y reiniciar el servicio
  (`docker compose restart ml-service`). El compose de desarrollo monta `./models`, así que el cambio rige al reiniciar.

## 4. Evaluación de la receta (preregistrada)

### 4.1 Features de calendario: no entran

La comparación es entre la receta vigente y la misma con las features de calendario y estacionalidad, las dos con la máscara de censura.
Se entrenó walk-forward con purge (run `evaluacion_receta`).

| Partición | Orígenes | Costo, con calendario frente a la vigente | WAPE, ídem | Cobertura con calendario |
|---|---|---|---|---|
| Temporada alta 2023-24 | 8 | +0,3 % [−1,0; +1,4] | +2,1 % [+1,5; +2,7] | 0,914 |
| Temporada alta 2024-25 | 8 | +3,3 % [+2,8; +3,8] | +2,3 % [+1,5; +3,0] | 0,904 |
| Temporada alta 2025-26 | 8 | +6,8 % [+5,1; +8,8] | +1,8 % [+1,2; +2,4] | 0,911 |
| Resto del año 2024 | 16 | +0,2 % [−0,8; +1,2] | +0,4 % [−0,2; +1,3] | 0,899 |
| Resto del año 2025 | 16 | +1,1 % [+0,6; +1,8] | +1,8 % [+1,1; +2,6] | 0,891 |
| Resto del año 2026 | 14 | +0,4 % [−0,3; +1,2] | +0,7 % [−0,1; +1,4] | 0,898 |

- **Regla preregistrada:** exige bajar el costo con intervalo por encima de 0 en las tres temporadas altas, no empeorarlo en el resto del
  año y cumplir WAPE y cobertura.
- **Lo que cumple:**
  - el resto del año, junto, no empeora: +0,6 % [+0,1; +1,1];
  - el WAPE y la cobertura cumplen;
  - dos temporadas altas ganan.
- **Lo que falla:** la temporada 2023-24 queda en +0,3 %, con un intervalo que cruza 0. Por eso **la receta sigue sin calendario** y
  `features.py` no cambia.
- **Lectura, sin decisión:**
  - la ganancia crece año a año (+0,3 %, +3,3 %, +6,8 %) y ninguna partición empeora;
  - la temporada que falla es la que tenía menos historia para la feature de «venta del año anterior», porque los datos empiezan en
    2022;
  - la confirmación prospectiva con las ventas de oct-2026 a ene-2027, preregistrada en el mismo protocolo, es la que puede cambiar
    esta decisión.
  - Adoptar el calendario ahora sería una excepción del equipo, que habría que declarar como tal.

### 4.2 Máscara de demanda censurada: entra, sin efecto medible

- **Alcance:** 577 eventos (pares con stock ≤ 0 en una foto y 15 días hábiles o más sin vender antes de ella) enmascaran 1.351 filas de
  523.976 (0,26 %).
- **Efecto sobre el costo en las filas que no enmascara:** −0,02 % [−0,17; +0,13].
- **Por qué entra:** por decisión del usuario, como protección. La corrección de fondo exige inventario diario o el registro de entradas.

### 4.3 Calibración adaptativa para la cabeza: no mejora (solo se reporta)

Simulación sobre las predicciones del holdout de 2026, rama intermitente, 18 orígenes (run `simulacion_calibracion`):

| Estrato | Cobertura: fijo (vigente) | Deslizante, 6 orígenes | Adaptativo, Gibbs y Candès | Costo, deslizante frente a fijo | Costo, adaptativo frente a fijo |
|---|---|---|---|---|---|
| Cabeza | 0,877 | 0,874 | 0,883 | −0,5 % [−2,0; +1,1] | −1,4 % [−2,9; −0,2] |
| Medio | 0,900 | 0,880 | 0,886 | −0,2 % [−0,6; +0,2] | −0,4 % [−0,9; −0,04] |
| Cola | 0,902 | 0,904 | 0,904 | −0,03 % [−0,05; 0,00] | −0,03 % [−0,05; 0,00] |
| Rama completa | 0,901 | 0,899 | 0,900 | −0,2 % [−0,6; +0,2] | −0,6 % [−0,9; −0,2] |

- El ajuste adaptativo sube algo la cobertura de la cabeza, pero empeora el costo, con un intervalo entero por debajo de 0.
- El deslizante no ayuda.
- El ajuste fijo vigente queda como el mejor de los tres.

## 5. Verificación de punta a punta (18-nov-2026)

Con el temporizador instalado (próxima corrida programada: lunes 23-nov a las 6:00), la unidad se disparó a mano. Es la misma que lanza
el temporizador, contra el DW de operación al 30-sep-2026 (catálogo vivo, 4.619 productos).

| Prueba | Resultado |
|---|---|
| Falla visible | La primera vez, un error del script (la limpieza de registros con `pipefail`) dejó la unidad en «failed» con código 2. Se corrigió en `f39695d` |
| Corrida completa | 9 min 18 s, código 0. Estado **«rechazado»**: frente al vigente, el costo queda en +0,05 % [−0,56; +0,69] (el intervalo cruza 0, no cumple), el WAPE mejora 1,5 % y la cobertura cumple. Es lo esperado: reentrenar la receta vigente con datos más recientes no demuestra mejora |
| Sin datos nuevos | La segunda corrida registra «sin datos nuevos» en 2 s, sin entrenar |
| Exportación del candidato | Con `--exportar-sin-regla` se creó la rama local `reentrenamiento/prueba-20261118-0951`: tres paquetes, metadatos y `SHA256SUMS`. `sha256sum -c` pasa y en MLflow quedó como «prueba_exportacion» |
| Reversa | En un contenedor aparte del servicio de predicción (puerto 8011, sin tocar el stack), el servicio carga el candidato y pronostica con «entrenado el 2026-11-18». Con los modelos vigentes, las huellas pasan y vuelve a «entrenado el 2026-09-25» |

**Ajustes tras la prueba:**

- los estratos del paquete se guardan como texto de Python, porque con texto de numpy los paquetes de las ramas suaves pasaban de 308 KB a
  770 KB;
- el commit y la salida en pantalla de una prueba de exportación la nombran como tal.

**Pruebas automáticas:** 43 en `notebooks/tests` (las de INV-63 más 14 del reentrenamiento), con 100 % de cobertura de los tres módulos de
funciones. Los módulos del orquestador que entrenan con datos reales se ejercitan en la corrida de punta a punta.
