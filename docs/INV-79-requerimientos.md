# INV-79 · Pronóstico para una fecha o un rango elegidos

**Tipo:** Error, Sprint 7 · **Fecha:** 18-nov-2026 · **Relacionadas:** INV-62 (pronóstico al día presente), INV-40 (Vera),
INV-80 (modelos propios de 7 y 30 días, Sprint 8).

## 1. Problema

La pantalla de predicciones y Vera solo dan los próximos 15 días hábiles desde hoy. La API acepta `fecha_corte` (un pronóstico
como se habría hecho en una fecha pasada), pero no está en la pantalla ni en Vera. No hay forma de pedir una fecha futura ni un
rango de otro largo. El usuario del negocio necesita cuatro cosas: elegir la fecha de inicio, un rango de otro largo, un día
puntual y un pronóstico pasado para compararlo con lo vendido.

## 2. Decisiones del usuario (formularios del 18-nov)

| Decisión | Qué se decidió |
| --- | --- |
| Alcance | Fecha elegida, pasada o futura, con el pronóstico real de 15 días hábiles; rangos de otro largo y días puntuales como mediana aproximada, sin cantidad de reposición |
| Modelos de 7 y 30 días | Fuera de este arreglo: historia INV-80 para el Sprint 8 |
| Vera | La hace la sesión de INV-40, con este mismo contrato |
| Registro | Issue tipo Error en el Sprint 7, antes del cierre del 20-nov |

## 3. Contrato

Aplica a `POST /api/ml/predict` del Core API, que reenvía la petición tal cual a `POST /api/predict` del servicio de predicción.

### 3.1 Petición: campos nuevos, opcionales

| Campo | Tipo | Qué es |
| --- | --- | --- |
| `fecha_inicio` | fecha | Primer día de la ventana. Sin ella, todo sigue como hoy: la ventana empieza después de la fecha de operación |
| `fecha_fin` | fecha | Último día de un rango. Puede ir sin `fecha_inicio`; entonces el rango empieza donde empieza la ventana por defecto |

`horizonte` sigue obligatorio y en 15. `fecha_corte` no se puede mezclar con `fecha_inicio` ni con `fecha_fin` (422).

### 3.2 Cómo se resuelve la fecha de inicio

Sea L el último día con datos de ventas.

- **Fecha pasada** (`fecha_inicio` hasta L): se pronostica con lo que se sabía el día hábil anterior a `fecha_inicio`.
  `fecha_datos` y `fecha_operacion` son ese día; la ventana son los 15 días hábiles siguientes, que empiezan en `fecha_inicio`
  (o en el día hábil siguiente si ese día no hubo ventas); `dias_habiles_sin_datos` es 0.
- **Fecha futura** (`fecha_inicio` después de L): las features salen del último dato y la ventana empieza en `fecha_inicio`
  (o en el día hábil siguiente, sin cierres programados). `dias_habiles_sin_datos` y `fuera_de_lo_medido` (más de 90) se
  calculan como en el pronóstico al día presente.
- La mediana (`prediccion_q50`) y la cantidad de reposición (`intervalo_confianza`) son siempre las de esa ventana de 15 días
  hábiles: son el pronóstico real del modelo.

### 3.3 Respuesta: campos nuevos

| Campo | Tipo | Qué es |
| --- | --- | --- |
| `ventas_reales_ventana` | número o null | Unidades vendidas en la ventana, solo si la ventana está entera dentro de la historia |
| `rango` | objeto o null | Solo si vino `fecha_fin` (sección 3.4) |

Se mantienen `fecha_datos`, `fecha_operacion`, `ventana_desde`, `ventana_hasta`, `dias_habiles_sin_datos` y
`fuera_de_lo_medido`.

### 3.4 El rango

`rango` = {`desde`, `hasta`, `dias_habiles`, `prediccion_q50_aproximada`, `metodo`, `ventanas`, `ventas_reales`,
`fuera_de_lo_medido`, `aproximado`: true}.

- **Días hábiles:** los de la historia y, después del último dato, los de `dim_tiempo` sin cierres programados.
- **«reparto»** (15 días hábiles o menos): la mediana de la ventana por días / 15. Un día puntual es la mediana / 15.
- **«ventanas_encadenadas»** (más de 15): ventanas de 15 días hábiles seguidas desde el inicio. Cada una se pronostica con las
  mismas features y el factor de calendario de sus días; la última se reparte.
- **`ventanas`:** lista, una entrada por ventana usada, recortada al rango: {`desde`, `hasta`, `dias_habiles`,
  `prediccion_q50_aproximada`, `ventas_reales`}. La suma de sus medianas da la del rango.
- **Sin cantidad de reposición, a propósito:** un cuantil no se puede repartir ni sumar. La de 7 y 30 días llega con INV-80.
- **`ventas_reales`** (del rango y de cada ventana): solo si el tramo está entero en la historia; si no, null.
- **`fuera_de_lo_medido`** del rango: la última ventana empieza más de 90 días hábiles después del dato con que se pronostica.

### 3.5 Errores

| Código | Cuándo |
| --- | --- |
| 422 | `fecha_corte` junto con `fecha_inicio` o `fecha_fin` |
| 422 | `fecha_fin` anterior al primer día de la ventana |
| 422 | Rango de más de 90 días hábiles |
| 422 | `fecha_inicio` o `fecha_fin` después del último día de `dim_tiempo` (hoy, 31-dic-2027) |
| 404 | Fecha pasada sin historia suficiente («historia insuficiente», como siempre) |

## 4. Pantalla de predicciones

- Dos fechas opcionales, «Desde» y «Hasta», junto a la sucursal. Vacías, la pantalla queda como hoy.
- Con una fecha pasada: la tarjeta «Vendido en la ventana», junto al pronóstico, para compararlos.
- Con un rango: la tarjeta del rango, con la mediana aproximada, sus días hábiles y lo vendido si ya pasó, marcada como
  aproximada y sin cantidad de reposición.

## 5. Criterios de aceptación (de Jira)

1. (obligatorio) La API acepta `fecha_inicio` y `fecha_fin` opcionales; sin ellas, el comportamiento no cambia.
2. (obligatorio) Con una fecha pasada, el pronóstico usa solo los datos hasta el día anterior y trae las ventas reales de la
   ventana si está completa.
3. (obligatorio) Con una fecha futura, la ventana empieza en esa fecha y la respuesta dice los días hábiles sin datos y el aviso
   de fuera de lo medido.
4. (obligatorio) Con un rango, la respuesta trae la mediana aproximada del rango, marcada como aproximada y sin cantidad de
   reposición; un rango de más de 90 días hábiles o mal formado da 422.
5. (obligatorio) La pantalla de predicciones permite elegir desde y hasta, y muestra el pronóstico, las ventas reales (si es
   pasado) y el rango aproximado.
6. (obligatorio) Vera pide pronósticos con fecha o con rango (sesión de INV-40).
7. (obligatorio) Pruebas automáticas, OpenAPI y documentación; integrado en develop por pull request y desplegado en staging.

## 6. Pruebas

- Funciones puras del rango, con la bodega falsa: inicio pasado y futuro, día de cierre, reparto, ventanas encadenadas,
  recorte de la última ventana, ventas reales completas e incompletas, fuera de lo medido.
- Endpoint del servicio de predicción: sin fechas igual que antes, fecha pasada, fecha futura, rango corto, rango largo, día
  puntual, y los 422.
- Core API: reenvío de los campos, respuesta con `rango`, mezcla con `fecha_corte`.
- Pantalla: fechas vacías igual que antes, fecha pasada con lo vendido, rango aproximado.
