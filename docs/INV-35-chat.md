# INV-35 · Vera, el chat integrado en la aplicación · Resultados y guía de pruebas

Requerimientos y decisiones: [`INV-35-requerimientos.md`](INV-35-requerimientos.md) (C1–C19 y Y1–Y5). Contrato que consume: [`INV-36-api-chat.md`](INV-36-api-chat.md) y §4.3 de [`INV-30-requerimientos.md`](INV-30-requerimientos.md) (v1.1).

## 1. Qué se entregó

```
AppShell (App.jsx)
 ├─ ChatProvider ── useChat ── enviarMensaje (src/api/chat.js) ── POST /api/chat/message (SSE)
 ├─ menú, encabezado y <Routes> (sin cambios)
 └─ VentanaChat (fija, no ocupa columna): BotonChat + PanelChat (carga diferida, 17,1 kB)
```

| Pieza | Dónde |
| --- | --- |
| **Cliente de streaming:** `fetch`, lector de SSE tolerante a fragmentos partidos (también a mitad de un carácter UTF-8), `: ping` ignorado, `AbortController`; ante un 401 renueva el token con `tryRefresh` y reintenta una vez (Y2) | `src/api/chat.js` (`client.js` solo exporta `tryRefresh`) |
| **Estado de la conversación:** `reposo → enviando → transmitiendo → reposo \| error`, más `espera` para el 429 (reintenta solo tras `Retry-After`, dos veces). Detener, reintentar y «Nueva conversación». Solo en memoria | `src/hooks/useChat.js` |
| **Lógica pura:** cómo cada evento arma el mensaje, la etapa visible, el historial que se envía (solo turnos completos y verificados, recortado a 13 mensajes y 16.000 caracteres, Y4) y el texto de cada error | `src/utils/chat.js` |
| **Ventana de Vera (Y3, revisada el 27-oct):** desde `sm` flota abajo a la derecha sin angostar la página (`aria-modal="false"`) y se maximiza sobre un fondo oscuro, con la conversación en una columna legible y lo de atrás `inert`; en el celular, pantalla completa y modal. Preguntas rápidas por rol (Y5) y sugerencias de `done` como botones; estados con las barras «pensando». La lista sigue lo que llega solo si el usuario no subió a leer | `src/components/chat/`, `src/hooks/useMedia.js` |
| **Datos estructurados:** cada `data` como tabla, con los valores tal como llegan (ya en es-CO y con su unidad); con varias tablas, solo la primera abierta; «Se muestran N de M» | `TablaDatos.jsx` |
| **Markdown seguro:** párrafos, negritas, código, listas y títulos como nodos de React; nunca HTML (Y1) | `Markdown.jsx`, `src/utils/markdown.js` |
| **Identidad de Vera** (paquete `vera-v2`): ícono y avatar dibujados en línea para animar las barras; paleta de InventAI/o; el teal solo en la barra alta; sin ámbar | `Vera.jsx`, `src/index.css` (`vera-pulso`, sin animación con «reducir movimiento») |

### Criterios de aceptación

| # | Criterio | Cómo se cumple |
| --- | --- | --- |
| 1 | Panel global, 3 roles, persiste entre rutas; lateral o pantalla completa | `ChatProvider` en `AppShell`, fuera de `<Routes>`. Ventana flotante o maximizada en vez de lateral (Y3 revisada). Pruebas en `App.test.jsx` y K-01, K-04, K-10, K-12 |
| 2 | Cliente con `fetch`, SSE, `AbortController`, detener y reintentar, en un módulo nuevo | `src/api/chat.js`, `useChat`. K-08 |
| 3 | Mensajes diferenciados, Markdown seguro | Usuario en `brand-blue`, Vera en `blue-50` con avatar. Prueba de `<img onerror>` y `<script>` |
| 4 | `data` como tabla con unidades del dato | `TablaDatos`. K-02, K-05 |
| 5 | Estados y error por código | Conectando, analizando, consultando (con la `etiqueta`), calculando recomendaciones (`lenta`), verificando; 429 «en espera»; 401, 403 (también el del `tool`), 422, 5xx y los códigos del evento `error`. K-02, K-06, K-11 |
| 6 | Herramientas consultadas y fecha del dato | Pie «Consultado: …» y «Datos al …» (`fechas_datos`, o la de los `data` si no llegó el `done`) |
| 7 | (S) Preguntas rápidas por rol y de seguimiento | `preguntasRapidas.js` (4 por rol, del conjunto v1) y `done.sugerencias` |
| 8 | Accesibilidad | Foco al abrir (campo) y al cerrar (botón); `role="log"` con `aria-live` y `aria-busy`; `role="status"` y `role="alert"`; Enter y Mayús+Enter; Escape cierra; `inert` en el celular y maximizada; contraste de la identidad (5,2:1 y 9,8:1) |
| 9 | Solo en memoria, «Nueva conversación», límite | Sin `localStorage`; 2.000 caracteres con contador; aviso al pasar de 6 turnos |
| 10 | Pruebas, cobertura, matriz y guía | §3; matriz de `frontend/README.md`; bloque K y corrida de la §19 en `INV-26-pruebas-pantallas.md` |
| 11 | (C) Persistencia | Fuera de la historia (INV-37) |

## 2. Hallazgos de la implementación

| # | Hallazgo | Qué se hizo |
| --- | --- | --- |
| H1 | Al pulsar «Detener» mientras se leía el cuerpo, la lectura fallaba con un `AbortError` que no es `ApiError`, y el panel mostraba «Vera no está disponible» | El hook ignora cualquier falla de un flujo que él mismo abortó. Prueba «detener a mitad del flujo…» |
| H2 | Entre `meta` y la primera herramienta el estado decía «Verificando la respuesta…», cuando el modelo todavía está eligiendo qué consultar | Etapa nueva `analizando` («Analizando tu pregunta…») |
| H3 | La fecha del dato salía tres veces: en el texto del modelo, en cada tabla y al pie | Solo al pie, una vez por respuesta. El agente sigue escribiendo «Datos al …» en el texto (es de su prompt): queda para el agente v3 |
| H4 | La pregunta rápida o la sugerencia que se pulsa desaparece y el foco caía al `body` | El foco vuelve al campo |
| H5 | El lema «Pregúntale a tu inventario» quedaba cortado por «Nueva conversación» | El botón queda con ícono, `aria-label` y `title` |
| H6 | En tablas de 6 columnas, el nombre del producto se partía en 4 líneas | Ancho mínimo de 8 rem en columnas de texto (la tabla se desplaza de lado) y panel de 32 rem desde `2xl` |
| H7 | Con relojes falsos, `waitFor` de Testing Library no avanza | Las pruebas del 429 usan `vi.advanceTimersByTimeAsync`, como `client.test.js` |

**Revisión del 27-oct** (pedida por el usuario: ventana flotante, maximizar, una franja blanca al desplazarse con el chat abierto y el responsive):

| # | Hallazgo | Qué se hizo |
| --- | --- | --- |
| H8 | A 1024 px el panel lateral dejaba al Dashboard en 500 px: tarjetas cortadas y textos que se salían. En tableta (820 px), Vera tapaba toda la pantalla | Ventana flotante desde `sm` (40 rem), fuera de la estructura de columnas: la página conserva su ancho. Pantalla completa solo por debajo de 40 rem |
| H9 | La franja blanca no se reprodujo en Chromium sin pantalla (1440 × 900, 1366 × 768, 1280 × 720, 1024 × 768, 820 × 1180 y 390 × 844: ningún contenedor de afuera quedó desplazado). Causas posibles en el código: `scrollIntoView` desplaza también los contenedores de afuera aunque tengan `overflow: hidden`; la rueda, al llegar al final del chat, pasaba a la página; y en el celular `h-screen` (100vh) incluye la barra del navegador | La lista se desplaza con su propio `scrollTop`, con `overscroll-contain` y `min-h-0`; la aplicación usa `h-dvh`. **Queda por confirmar con el usuario** en su navegador |
| H10 | En el celular el botón de Vera tapaba la paginación de Alertas e Inventario al final de la página | `pb-20` en el contenido de las páginas |
| H11 | La lista bajaba al final con cada fragmento aunque el usuario hubiera subido a leer | Solo sigue lo que llega si está a menos de 48 px del final; una pregunta nueva vuelve a seguirlo |

### Mejoras del 27-oct (M1–M8, fuera de Jira)

Plan y criterios: §8 de [`INV-35-requerimientos.md`](INV-35-requerimientos.md).

| # | Resultado |
| --- | --- |
| M1 | **Preguntas rápidas validadas** contra el agente real: 32 corridas (las 12 rápidas y 12 alternativas del v1; las de `admin_sucursal` con PRINCIPAL y con LA 21). Fallaron 2: «Dame un reporte general de las alertas por nivel» con el gerente terminó **otra vez en respaldo** (cuatro llamadas a `resumen_alertas`), y la alternativa «Dame un reporte de ventas» con `admin.principal` (H12). La primera se cambió por «Dame un ranking de alertas por sucursal», la misma intención, que pasó 4 de 4. Las otras 11 quedan igual. «Dame un reporte de ventas de los últimos 90 días» pasó con `fidelidad: reintento` |
| M2 | **Aviso de demora** en `useChat` (`demorado`, 10 s sin eventos) y en el estado del panel. En vivo, con el modelo descargado de la GPU (`ollama stop qwen3:8b`): la respuesta tardó 51 s y a los 11,5 s se leía «Está tardando más de lo normal…» |
| M3 | **`saludVera`** en `chat.js` (no `apiFetch`: descarta el `{motivo}` del 503), con `useConsulta` al abrir el panel. En vivo, con `docker stop inventaio-nlp-agent`: «Vera no está disponible · El servicio de Vera no responde», preguntas rápidas y envío deshabilitados; tras `docker start` y «Volver a comprobar», el envío vuelve |
| M4 | **CSV por tabla** (`utils/tablaVera.js` sobre `csv.js`). En vivo: `vera-resumen-de-alertas-principal.csv` con `Sucursal;Crítica;Alta;Media;Total` y `PRINCIPAL;297;138;873;1308`. Las columnas `cantidad` ahora se alinean a la derecha |
| M5 | **«Respondió en X s»** al pie, junto a la fecha del dato. En frío: «Respondió en 51,5 s» |
| M6 | **`useTitulo`**: «Dashboard · InventAI/o», «Alertas · InventAI/o»…; «Iniciar sesión · InventAI/o» en el login |
| M7 | **«Preguntar a Vera» en cada tarjeta de Alertas** (reglas y con IA): el ícono de Vera (identidad `vera-v2`), sin texto, a la derecha del detalle, con la pregunta en el *tooltip* y en el nombre accesible (el texto «Preguntar a Vera» se cambió por el ícono a pedido del usuario el 27-oct). Con `BotonPreguntarVera` y `usePreguntarAVera` (fuera de `ChatProvider` no se muestra). La pregunta sale de `preguntaDeAlerta`: reglas → «¿Cómo está el inventario de X en S?»; riesgo con IA → «¿Alcanza el stock de X en S para los próximos 15 días hábiles?»; sobrestock con IA → «¿Cuál es el pronóstico de X en S?». Validadas con el gerente, `admin.norte`, `admin.principal` y la Bodega (también en BODEGA_CENTRAL); en vivo con `admin.norte`, en las dos pestañas. **Recomendaciones quedó fuera** (H13) |
| M8 | README: la nota de Nginx ya no dice que `/api/chat/` es de INV-36 |

| # | Hallazgo | Qué se hizo |
| --- | --- | --- |
| H13 | **Del agente:** las preguntas por producto de Recomendaciones no son confiables. «¿Qué traslados hay de DURAZNO…?» con la Bodega respondió «no hay traslados hacia la BODEGA_CENTRAL» (asumió la dirección por el rol; el traslado sale de la Bodega hacia GLORIETA); con origen y destino explícitos respondió «no hay» en 3 de 4 y dio 403 a `admin.principal` (filtró por el origen, que no es su sucursal). `recomendar_compras` no filtra por producto: «¿Por qué se sugiere comprar X?» respondió con las 296 líneas | M7 solo en Alertas. Para el agente v3: filtro por producto en compras y la dirección del traslado sin asumirla por el rol |
| H12 | **Del agente, no del panel:** con `admin.principal`, «Dame un reporte de ventas» respondió en 340 ms el texto literal `<reporte> ventas </reporte>`, sin herramientas y con `fidelidad: ok` (no hay cifras que verificar). Con `admin.norte` la misma pregunta salió bien | Vera lo muestra como texto (sin HTML). Queda para el agente v3: el verificador debería exigir herramientas cuando la pregunta pide datos |

## 3. Verificación (24-oct; revisión y mejoras del 27-oct)

- **Vitest: 302 pruebas en verde** (32 archivos); 79 son nuevas: lector de SSE con fragmentos partidos, cliente (401 con renovación, 429, 422, sin conexión, cancelada), lógica pura, hook (máquina de estados, 429 con relojes falsos, detener, cortes), componentes por rol, ventana flotante, maximizada y en pantalla angosta, el seguimiento del final de la lista, y las mejoras M2 a M7 (demora con relojes falsos, salud con cada motivo, conversión a CSV, tiempo, título y el botón de Alertas). Cobertura total del 98 %; los archivos nuevos, entre 87 % y 100 % de ramas.
- **ESLint:** sin avisos nuevos (siguen los 3 de deuda de `useConsulta`). **Build:** `PanelChat` va en su propio archivo (17,1 kB; 5,9 kB comprimido); el ícono de Vera, que ahora usa también Alertas, va aparte.
- **De punta a punta** contra el stack real (Nginx en el 8080 y Vite en el 5173, `qwen3:8b`), con Chromium sin pantalla:
  - gerente: alertas críticas de GLORIETA (243, con tabla, en unos 5 s), traslados hacia PRINCIPAL («Se muestran 10 de 88.») y su sugerencia de seguimiento, que conserva la sucursal (compras de PRINCIPAL), y ventas de 90 días;
  - `admin.norte`: GLORIETA con 403 dentro del flujo («(sin permiso)», sin tabla ni sugerencias);
  - `admin.principal`: alertas de su sucursal; `bodega`: estado general;
  - 24-oct: 1440 × 900 (panel lateral, ya reemplazado) y 390 × 844 (pantalla completa);
  - 27-oct, con la ventana flotante: 1440 × 900, 1024 × 768 y 820 × 1180, flotante y maximizada; 390 × 844 a pantalla completa; y la paginación de Alertas e Inventario libre del botón en el celular.
  - 27-oct, mejoras: las 32 corridas de M1, el modelo en frío (M2 y M5), el agente detenido y recuperado (M3, K-11), la descarga del CSV (M4), el título (M6) y «Preguntar a Vera» desde Alertas (M7, 4 + 11 corridas de plantillas).
- **Sin probar en vivo:** el 429 con dos pestañas; lo cubren las pruebas de Vitest.

## 4. Cómo probarlo

```bash
cd ~/InventaIO/frontend && npm run test:cov       # o desde el worktree de la rama
npm run dev                                       # http://localhost:5173, con el stack del 8000 arriba
```

La guía para el navegador es el bloque K de [`INV-26-pruebas-pantallas.md`](INV-26-pruebas-pantallas.md), y su corrida con capturas, la §19.

## 5. Fuera de la historia

- **Persistencia del historial** (INV-37) y **PWA** (A3): no hay *service worker* ni instalación.
- `GET /api/chat/health` no se consume: la falta del agente se ve al enviar.
- La identidad completa de Vera (logo horizontal, endoso, favicon) no se versiona: el paquete `vera-v2` queda como referencia.
