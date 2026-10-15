# INV-28 · Alertas inteligentes ML · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-28 «Alertas inteligentes ML» · 5 SP · Sprint 6 · Release 2 · épica E9 ML Dashboard (INV-54) |
| Depende de | INV-22 (balance de traslados), INV-23 (cliente, caché y filtros de `api/ml/`), INV-25 (permisos por ubicación e `inconsistencia_inventario`), INV-26 e INV-27 (base del frontend) |
| Alimenta a | INV-32 (las herramientas del agente consultarán estas alertas) |
| Rama | `feature/INV-28-alertas-ml`, desde `develop` (`44fc71b`) |
| Datos | Foto de inventario del 31-dic-2025; políticas de INV-21 e INV-22 en su versión 1 (2026-09-30) |

Revisión del 9 de octubre de 2026, verificada de nuevo el 15 de octubre contra `develop` y la bodega real: las cifras se reproducen exactas.

## 1. Historia de Jira

> Como administrador de bodega, quiero alertas basadas en predicciones ML, para anticiparme a problemas de stock.
>
> 1. Alertas ML: riesgo de desabastecimiento, sobrestock previsto. 2. Integradas con alertas por reglas. 3. Badge «IA» diferenciando tipo.

La ficha tiene solo la plantilla original (historia, 3 criterios y el DoD general). No dice qué es «riesgo», qué es «sobrestock», cómo convivir con las alertas por reglas ni de dónde salen los datos. Este documento lo fija.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | Las alertas por reglas (`api/alertas/router.py`, INV-7 e INV-25) se calculan con SQL al vuelo. Para el gerente son 4.452: `inconsistencia_inventario` 220, `stock_critico` 1.114, `stock_bajo` 386, `sin_movimiento` 2.453 y `rotacion_baja` 279 | Responden en menos de 1 s; no deben heredar la espera del ML |
| C2 | No hace falta un modelo nuevo. El balance de INV-22 trae, por producto y ubicación, `q50`, `maximo`, `excedente`, `dias_hasta_agotarse` y `urgencia` (≤ 5 días hábiles urgente, ≤ 10 alta), calculados sobre el stock de la foto **antes** de los traslados sugeridos | La alerta reutiliza esas cifras; no se recalcula ningún pronóstico |
| C3 | Riesgo según el ML en sucursales (urgente o alta): 1.528 pares. De ellos, 943 tienen stock ≤ 0 (134 negativos, ya cubiertos por `inconsistencia_inventario`) y solo 957 esperan vender al menos 1 unidad en 15 días | Hay que filtrar: sin eso la alerta repite lo que ya dicen las reglas o avisa por demandas de 0,6 unidades |
| C4 | El excedente de la Bodega Central (1.415 pares) es por diseño: no vende. Los pares con q50 = 0 y stock > 0 (494) ya los cubre `sin_movimiento` | El sobrestock de ML se limita a sucursales con demanda prevista |
| C5 | El balance tarda 20 a 42 s en frío (medido el 15-oct: 42 s) y 0,04 a 0,5 s con la caché de INV-23 (TTL 6 h) | Endpoint aparte (V1) |
| C6 | La caché de INV-23 siempre guarda la respuesta de transferencias **con** balance: Recomendaciones y las alertas de ML comparten la misma entrada | Si alguien abrió Recomendaciones, las alertas salen al instante, y al revés |
| C7 | `AlertaItem` no tiene campo de origen y `TIPOS` rechaza los tipos desconocidos con 400 | El contrato de `/api/alertas` no se toca; el de ML es propio |
| C8 | El balance identifica el producto por `codigo_item`; las alertas por reglas, por `id_producto`. `CatalogoBodega.productos()` no devuelve el id | Hace falta el cruce `codigo_item → id_producto` (una consulta a `dw.dim_producto`) |
| C9 | Predicciones redondea los días a un decimal antes de comparar con 5 y 10; el balance calcula la urgencia sin redondear y entrega los días ya redondeados a un decimal (pendiente de negocio en `docs/CORRECCIONES.md`) | Las alertas usan la urgencia del balance (V11). Un par cae en el borde: HUEVOS en LA 21 (5,026 días) es «alta» aquí y en Recomendaciones, y «Urgente» en Predicciones. Redondeando, el reparto sería 484 críticas y 382 altas |
| C10 | La Bodega no tiene pronóstico | No genera alertas de ML |

## 3. Decisiones

| Código | Tema | Decisión |
| --- | --- | --- |
| V1 | Integración | Endpoint aparte `GET /api/alertas/ml` y una sección «Alertas con IA» en la pantalla de Alertas. Las de reglas aparecen al instante y las de IA cuando llegan, con aviso de espera y «Reintentar». `/api/alertas`, `/api/alertas/resumen` y el Dashboard no cambian |
| V2 | Solapamiento | Una fila por par producto-sucursal y tipo de ML, con campo `origen`: `ambos` si las reglas ya marcan el par con `stock_critico` o `stock_bajo`, `ml` si solo lo ve el modelo. El sobrestock siempre es `ml` (V6) |
| V3 | Riesgo de desabastecimiento | Sucursal física, urgencia del balance `urgente` o `alta`, **q50 ≥ 1** en 15 días y **stock ≥ 0**: 866 alertas (483 urgentes y 383 altas); 395 `ambos` y 471 `ml`. PRINCIPAL 437, GLORIETA 246, LA 21 183 |
| V4 | Sobrestock previsto | Sucursal física, **stock > 2 × máximo**, q50 > 0 y stock > 0: 721 alertas (PRINCIPAL 368, GLORIETA 216, LA 21 137). El máximo es el de INV-22: max(qα × (1 + margen), q50) |
| V5 | Tipos y urgencia | `riesgo_desabastecimiento_ml`: urgente → `critica`, alta → `alta`. `sobrestock_previsto_ml`: `media`, como `rotacion_baja` |
| V6 | Sobrestock y `sin_movimiento` | Se muestran las dos: los 130 pares que cumplen ambas dicen cosas distintas (demanda prevista frente a ventas pasadas) |
| V7 | Permisos | Los de INV-25: `gerente` y `admin_bodega` ven todo; `admin_sucursal` solo su sucursal (403 si pide otra) |
| V8 | Fuente | `api/ml/`: el mismo cliente, la misma caché y los mismos filtros de INV-23. Ninguna llamada nueva al ML Service |
| V9 | Distintivo «IA» | Todas las filas de la sección llevan «IA»; las `ambos` dicen además «también por reglas» |
| V10 | Stock base del riesgo | El de la foto, antes de los traslados sugeridos. Si el par recibe un traslado, el detalle lo dice («traslado sugerido de N desde X»). Hoy son 100 alertas con traslado y 35 que el traslado cubriría por completo; no se ocultan porque dependen de que alguien lo ejecute |
| V11 | Redondeo de los días | Sin redondear: la urgencia se toma tal como la entrega el balance, igual que Recomendaciones. Afecta a HUEVOS en LA 21 (alta, 5,0 días mostrados) |
| V12 | Pantalla | Pestañas «Por reglas» y «Con IA» en la página Alertas, como en Recomendaciones (decisión del 15-oct, tras ver la primera versión con la sección debajo de las 50 alertas de reglas). Solo se consulta la pestaña abierta: la de reglas sigue al instante y la espera del ML solo ocurre al elegir la de IA. Cada pestaña tiene sus tarjetas de resumen (las de IA: total, riesgo, sobrestock y «también por reglas», sin los filtros de tipo, urgencia y origen) y conserva sus filtros al cambiar de una a otra |

## 4. Entradas, salidas e interfaz

**Entradas.** Token JWT. Filtros opcionales `sucursal_id`, `tipo` (`riesgo_desabastecimiento_ml` o `sobrestock_previsto_ml`; otro valor da 422), `urgencia`, `origen`, `page` y `page_size` (como en el fix de INV-26). Datos: el balance de INV-22 por la caché de INV-23 y la foto de inventario.

**Salida de `GET /api/alertas/ml`.**

```json
{
  "items": [{
    "id_producto": 91, "codigo_item": "P1632", "nombre_producto": "HUEVOS *UND", "categoria": "Huevos",
    "sucursal": "PRINCIPAL", "id_sucursal": 1, "tipo_ubicacion": "sucursal",
    "tipo": "riesgo_desabastecimiento_ml", "urgencia": "critica", "origen": "ambos",
    "valor": 2.2, "umbral": 5.0, "unidad": "unidad",
    "stock": 489.0, "q50": 3366.01,
    "detalle": "Stock 489 unidades; con la demanda prevista (3.366 unidades en 15 días hábiles) alcanza 2,2 días hábiles; traslado sugerido: …",
    "fecha": "2025-12-31"
  }],
  "total": 1587, "page": 1, "page_size": 50, "pages": 32,
  "resumen": {"total": 1587, "riesgo_desabastecimiento_ml": 866, "sobrestock_previsto_ml": 721, "critica": 483, "alta": 383,
              "media": 721, "ambos": 395, "ml": 1192},
  "fecha_inventario": "2025-12-31", "politicas": {"version": 1, "fecha": "2026-09-30"},
  "calculado_en": "2026-10-15T15:00:00Z"
}
```

`politicas` es la versión de las políticas de INV-22 con que se calculó el balance. `valor` es `dias_hasta_agotarse` en el riesgo y `stock / maximo` en el sobrestock; `umbral` es 5 o 10 en el riesgo y 2 en el sobrestock. El orden es por urgencia y, dentro de ella, lo más grave primero: menos días en el riesgo, más veces el máximo en el sobrestock.

**Errores.** 401 o 403 sin token (como el resto del Core API), 403 por ubicación ajena, 422 por parámetros inválidos y los del ML Service traducidos como en INV-23: 409 (foto sin ventas), 502, 503 y 504.

**Interfaz.** En la página Alertas, las pestañas «Por reglas» (abierta al entrar) y «Con IA» (V12). La pestaña «Con IA» tiene tarjetas de resumen, filtros de tipo, urgencia y origen, paginación de 50 en 50, distintivo «IA» en cada tarjeta, aviso de espera («La primera consulta calcula el pronóstico de toda la red: tarda cerca de 30 s.») y un solo mensaje de error con «Reintentar». Respeta el selector de sucursal de la página. El Dashboard no cambia.

## 5. Criterios de aceptación

1. `GET /api/alertas/ml` devuelve los dos tipos con las reglas V3 y V4, y con la foto del 31-dic-2025 da 866 de riesgo (483 críticas y 383 altas) y 721 de sobrestock.
2. Cada fila trae `origen`: 395 `ambos` y 471 `ml` en el riesgo; el sobrestock siempre `ml`.
3. Las urgencias siguen V5 y los días se comparan sin redondear (V11).
4. `/api/alertas`, `/api/alertas/resumen` y el Dashboard no cambian de contrato ni de tiempo de respuesta.
5. Permisos de INV-25: `admin_sucursal` solo ve su sucursal (403 si pide otra) y la Bodega no genera alertas de ML.
6. El riesgo usa el stock de la foto y el detalle menciona el traslado sugerido cuando lo hay (V10).
7. La página Alertas tiene las pestañas «Por reglas» y «Con IA» y solo consulta la abierta (V12). La de IA muestra resumen, distintivo, filtros, paginación, aviso de espera y «Reintentar» ante 409, 502, 503 y 504; los rótulos salen de `etiquetas.js`.
8. Sin llamadas nuevas al ML Service: las alertas comparten la caché con Recomendaciones.

## 6. Casos de prueba (datos reales)

| Caso | Entrada | Resultado esperado |
| --- | --- | --- |
| P-01 | HUEVOS *UND (P1632) en PRINCIPAL: stock 489, q50 3.366 | `riesgo_desabastecimiento_ml`, crítica, `origen = ambos` (las reglas lo marcan `stock_critico`, cobertura 2,9 d) |
| P-02 | BLQ CLOROX RC1800+CLOROX RC 930 (00037) en PRINCIPAL: sin fila en la foto (stock 0 en el balance), q50 1,86 | Riesgo crítico, `origen = ml` |
| P-03 | CHOCOLAT JET BURBUJA *12 UND (00002) en LA 21: stock 0, q50 0,66 | Sin alerta de ML (q50 < 1) |
| P-04 | AGUA CRISTAL LITRO SPORT (00008) en LA 21: stock −1 | Sin alerta de ML; sí `inconsistencia_inventario` en reglas |
| P-05 | CONDIMENTO EL TIZON * 50 GR (01108) en GLORIETA: stock 404, máximo 18,36 | `sobrestock_previsto_ml`, media, `origen = ml` |
| P-06 | Un par con q50 = 0 y stock > 0 | Sin sobrestock de ML; sí `sin_movimiento` |
| P-07 | Un par con riesgo y traslado sugerido desde la Bodega | Alerta presente; el detalle nombra el traslado (V10) |
| P-08 | Bodega Central | Sin alertas de ML |
| P-09 | Totales sin filtros (gerente) | 866 de riesgo (483 + 383; 395 `ambos`) y 721 de sobrestock |
| P-10 | `admin_sucursal` de LA 21 | Solo LA 21 (183 de riesgo y 137 de sobrestock); con `sucursal_id` de otra sucursal, 403 |
| P-11 | `tipo=stock_bajo` | 422 |
| P-12 | Sin token | 403 |
| P-13 | ML Service caído | 503 con mensaje en español; en pantalla, «Reintentar» |
| P-14 | `/api/alertas` y `/api/alertas/resumen` | Mismo contrato y menos de 1 s, con la caché de ML vacía |
| P-15 | HUEVOS *UND (P1632) en LA 21: 5,026 días hábiles | Riesgo `alta`, valor 5,0, umbral 10 (V11) |

## 7. Ruta de implementación

Un commit por paso en `feature/INV-28-alertas-ml`, con las pruebas en verde antes de pasar al siguiente, igual que INV-25 a INV-27.

1. **Requerimientos.** Este documento.
2. **Core API.** Esquemas `AlertaMLItem` y `AlertaMLList` en `api/schemas/alertas.py`; el cruce `codigo_item → id_producto` (C8) en `api/ml/catalogo.py`; `api/alertas/ml.py` con las reglas V2 a V6, V10 y V11, que lee el balance con `obtener_recomendaciones("transferencias", …)` de INV-23; la ruta `GET /api/alertas/ml` con permisos, filtros, paginación y errores. Pruebas unitarias con transporte httpx falso (sin Postgres ni ML Service) y de integración con la marca `integracion` para P-09 y P-10.
3. **Contrato.** OpenAPI versionado regenerado (lo comprueba el CI), casos nuevos en la colección de Postman y `api/tests/test_alertas_ml.sh`.
4. **Frontend.** `getAlertasML` en `client.js` con `conTimeoutML`; etiquetas en `etiquetas.js`; las pestañas en `Alertas.jsx` con `useConsulta` (`activo` según la pestaña) y `EstadoConsulta`; pruebas de Vitest con el umbral de 80 %.
5. **Pantallas.** Bloque nuevo en `docs/INV-26-pruebas-pantallas.md` y corrida con Playwright y capturas (evidencia local, fuera de git), con los tres roles.
6. **Documentación.** `docs/INV-28-alertas-ml.md` y la matriz endpoint → pantalla de `frontend/README.md`.
7. **Cierre.** Merge `--no-ff` a `develop`, push y CI en verde cuando el dueño lo pida; luego, la ficha de Jira con estos criterios y el cierre.

## 8. Definition of Done

Además del DoD general del proyecto: los totales de P-09 reproducidos contra la bodega real; los 15 casos de la sección 6 verificados; el OpenAPI regenerado sin diferencias en el CI; la cobertura de Vitest y del Core API sobre los umbrales del CI; verificado con los tres roles en el navegador.

## 9. Fuera de alcance y riesgos

- **Fuera de alcance:** exportar las alertas de IA a CSV; mostrarlas en el Dashboard; recalcular el balance con el stock tras los traslados; el redondeo unificado de los días (decisión de negocio pendiente); precalentar la caché al arrancar.
- **Primera consulta lenta:** 20 a 42 s en frío; se mitiga con V1, las pestañas (V12) y el aviso de espera, no se resuelve aquí.
- **Utilidad de las 471 alertas que solo ve el ML:** no está validada con el negocio; conviene que revise una muestra.
- **Foto única:** las alertas describen el 31-dic-2025, no un stock en vivo.
- **Estimación:** se mantienen los 5 SP; no hay modelo nuevo y la base (caché, permisos, componentes) ya existe.
