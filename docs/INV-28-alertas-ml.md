# INV-28 · Alertas inteligentes ML

`GET /api/alertas/ml` y la pestaña **«Con IA»** de la página Alertas avisan
de dos riesgos que las reglas de inventario no ven: un producto que se va a agotar
según la demanda prevista y un sobrestock frente a esa demanda. No hay modelo nuevo:
las cifras salen del balance de traslados de INV-22 (pronóstico q50, máximo y días
hábiles hasta agotarse), que el Core API ya guarda en la caché de INV-23.

La especificación, con el contraste C1–C10 y las decisiones V1–V11, está en
[`INV-28-requerimientos.md`](INV-28-requerimientos.md). Este documento dice cómo quedó
implementada y cómo se verificó.

## Qué se entregó

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| Reglas | `api/alertas/ml.py` | Funciones puras sobre la respuesta de transferencias: `generar_alertas_ml` (V2 a V6, V10 y V11) y `resumen_alertas_ml`. No modifican lo que guarda la caché |
| Ruta | `api/alertas/router_ml.py` | `GET /api/alertas/ml`: permisos de INV-25, filtros, paginación y resumen. `ReglasInventario` lee las ubicaciones y los pares que las reglas marcan en riesgo |
| Esquemas | `api/schemas/alertas.py` | `AlertaMLItem`, `AlertaMLResumen` y `AlertaMLList`, con `tipo`, `urgencia` y `origen` como enumeraciones (un valor fuera de ellas da 422) |
| Cruce de ids | `api/ml/catalogo.py` | `CatalogoBodega.ids_producto()`: `codigo_item → id_producto` (C8) |
| Cliente | `frontend/src/api/client.js` | `getAlertasML`, con la espera de 130 s de las consultas de ML |
| Página | `frontend/src/pages/Alertas.jsx` | Pestañas «Por reglas» y «Con IA» (V12); la de IA con tarjetas de resumen, filtros, paginación y estados; tarjeta y paginación compartidas entre las dos |
| Distintivo | `frontend/src/components/DistintivoIA.jsx` | La marca «IA» (V9) |
| Filtros con casillas | `frontend/src/components/FiltroMultiple.jsx` | Desplegable con casillas para varios valores (V13): resume la selección («Todos los tipos», el nombre o «2 tipos») y se cierra con Escape o con un clic fuera |
| Varios valores en el API | `api/alertas/router.py` y `router_ml.py` | `tipo` y `urgencia` (y `origen` en ML) aceptan el parámetro repetido; `buildQS` del cliente repite el parámetro cuando recibe una lista |
| Etiquetas | `frontend/src/utils/etiquetas.js` | `TIPOS_ALERTA_ML` y `ORIGENES_ALERTA_ML`; `etiquetaTipoAlerta` conoce los tipos nuevos |

`/api/alertas/resumen`, el Dashboard y `ml_service` no cambian. `/api/alertas` solo cambia en que sus filtros aceptan varios valores (V13); un solo valor responde igual que antes.

## Cómo funciona

**Datos.** `GET /api/alertas/ml` pide el resultado de transferencias con
`obtener_recomendaciones("transferencias", …)` de INV-23: misma clave de caché (foto y
versiones de políticas) y mismo TTL de 6 h. Si alguien abrió Recomendaciones, las
alertas salen al instante, y al revés. La primera consulta tras reiniciar el Core API
tarda de 20 a 40 s (42 s medidos el 15-oct en la máquina de desarrollo).

**Reglas** (solo sucursales físicas; la Bodega no tiene pronóstico):

| Tipo | Condición | Urgencia | `valor` y `umbral` |
| --- | --- | --- | --- |
| `riesgo_desabastecimiento_ml` | Urgencia del balance `urgente` (≤ 5 días hábiles) o `alta` (≤ 10), q50 ≥ 1 y stock ≥ 0 | `critica` o `alta` | Días hasta agotarse; 5 o 10 |
| `sobrestock_previsto_ml` | Stock > 2 × máximo de INV-22, q50 > 0 y stock > 0 | `media` | Stock ÷ máximo; 2 |

**Origen.** `ambos` cuando las reglas ya marcan el par con `stock_critico` o
`stock_bajo` (mismas condiciones que `/api/alertas`); `ml` en los demás casos. El
sobrestock siempre es `ml`: no se fusiona con `sin_movimiento` (V6).

**Detalle.** El riesgo se calcula con el stock de la foto, antes de los traslados
sugeridos (V10); si el par recibe uno, el texto lo nombra: «Stock 256 unidades; con la
demanda prevista (828 unidades en 15 días hábiles) alcanza 4,6 días hábiles; traslado
sugerido: 572 unidades desde BODEGA_CENTRAL».

**Redondeo (V11).** La urgencia es la del balance, calculada sin redondear; el balance
entrega los días ya redondeados a un decimal. Un par cae en el borde: HUEVOS \*UND en LA
21 (5,026 días) es «Alta» aquí y en Recomendaciones, y «Urgente» en Predicciones, que
redondea antes de comparar. Está anotado como decisión de negocio pendiente en
[`CORRECCIONES.md`](CORRECCIONES.md).

**Orden.** Por urgencia; dentro de ella, menos días primero en el riesgo y más veces el
máximo primero en el sobrestock.

**Permisos.** Los de INV-25 para alertas: `gerente` y `admin_bodega` ven todo;
`admin_sucursal` solo su sucursal (403 si pide otra o la Bodega). Se resuelven antes de
llamar al ML Service.

**Pantalla (V12).** La página Alertas abre en la pestaña «Por reglas», que no espera al
modelo. La pestaña «Con IA» solo se consulta al abrirla (`useConsulta` con `activo`) y
tiene: tarjetas de resumen (total, riesgo, sobrestock y «también por reglas») que solo
cambian con la sucursal, como las de reglas; filtros de tipo, urgencia y origen; páginas
de 50; el aviso de espera a los 5 s; un solo mensaje de error con «Reintentar», que
repite la lista y el resumen; y un mensaje sin alertas que explica por qué la Bodega no
las genera. Los filtros son desplegables con casillas y admiten varios valores (V13). Cada pestaña conserva sus filtros al cambiar de una a otra; «Actualizar»
repite solo la abierta; cambiar la sucursal o un filtro vuelve a la primera página.

## Cifras con la foto del 31-dic-2025

| | Riesgo | Sobrestock | Total |
| --- | --- | --- | --- |
| Toda la red | 866 (483 críticas, 383 altas; 395 `ambos`) | 721 | 1.587 |
| PRINCIPAL | 437 | 368 | 805 |
| GLORIETA | 246 | 216 | 462 |
| LA 21 | 183 | 137 | 320 |

Del riesgo, 100 alertas tienen un traslado sugerido y 35 quedarían cubiertas del todo si
se ejecuta. De los sobrestocks, 130 también son `sin_movimiento` en las reglas.

## Verificación

| Qué | Resultado |
| --- | --- |
| Pruebas unitarias del Core API (`tests/test_alertas_ml.py`, sin Postgres ni ML Service) | 24 nuevas; 178 unitarias en total. Cobertura: `alertas/ml.py` 100 %, `alertas/router_ml.py` 88 % (lo que falta son las consultas a la bodega, que cubre la integración) |
| Integración con la bodega real (`tests/test_alertas_ml_integracion.py`) | 6 pruebas: cifras de la tabla, casos con productos reales, traslados nombrados, `admin.norte`, `/api/alertas` sin cambios y varios valores por filtro (1.500 = stock crítico + bajo; 866 = críticas + altas con IA). Suite completa del Core API: 240 |
| Script con curl (`api/tests/test_alertas_ml.sh`) | 31 de 31 |
| Postman (`api/tests/postman/INV-28.postman_collection.json`, Newman) | 20 peticiones, 58 verificaciones, 0 fallas; la colección de INV-25 sigue en 182 sin fallas |
| Regresión de las alertas por reglas (`test_alertas.sh`) | 39 de 39 |
| OpenAPI versionado | Regenerado; solo agrega la ruta y sus esquemas |
| Frontend (Vitest) | 17 pruebas nuevas (pestañas, filtros con casillas y cliente); 221 en total, 98,39 % de líneas. ESLint con los 3 avisos conocidos de `useConsulta`; build sin errores |
| Pantallas (sección 17 de la guía, Playwright) | 21 de 21: bloque E de regresión (con E-09, varios valores) y bloque J (con J-12), con carga en frío (la pestaña de reglas no consulta al modelo; la de IA tardó 19 s) y el ML Service detenido |

## Pendientes y riesgos

- **Primera consulta lenta** (20 a 42 s): se mitiga con la pestaña aparte y el aviso; precalentar la caché al arrancar queda fuera.
- **Las 471 alertas que solo ve el modelo** no están validadas con el negocio.
- **Foto única:** las alertas describen el 31-dic-2025, no un stock en vivo.
- **Fuera de alcance:** exportar a CSV, mostrarlas en el Dashboard y unificar el redondeo de los días.
