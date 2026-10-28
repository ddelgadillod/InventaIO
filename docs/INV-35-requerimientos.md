# INV-35 · Vera, el chat integrado en la aplicación · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-35 · 8 SP · Sprint 6 · Release 2 · épica E12 Chat PWA (INV-57) |
| Depende de | INV-36 (`POST /api/chat/message`, Finalizada), INV-30/32/33 (contrato v1.1 del agente), INV-26 (base del front) |
| Rama | `feature/INV-35-chat-panel`, desde `develop` (`1ca1725`), en el worktree `~/InventaIO-wt/INV-35` |
| Identidad | **Vera**, «la asistente de InventAI/o» (decisión del 24-oct). Paquete `vera-v2` en Descargas; la sección 4.1 fija cómo se usa |
| Fechas | Congelamiento de código el 30-oct; vence el 31-oct |
| Contingencia | Si va atrasada: panel sin preguntas rápidas ni pulido móvil, pero con streaming, datos estructurados y permisos |

Revisión del 24-oct-2026 contra `develop` y el traspaso de INV-33. Estado: decisiones Y1 a Y4 tomadas el 24-oct (todas como se propusieron); Y5 se toma como propuesta por ser menor. **Y3 se revisó el 27-oct:** ventana flotante que se puede maximizar (ver la tabla). Implementada el mismo día: resultados y hallazgos H1–H7 en [`INV-35-chat.md`](INV-35-chat.md).

## 1. Historia de Jira

> Como usuario autenticado, quiero un chat dentro de la aplicación que me responda en streaming y me muestre los datos consultados, para preguntarle al agente sin salir de la pantalla en que estoy.

La ficha trae 9 criterios (M), uno (S) y uno (C). Este documento los contrasta con el repositorio y fija lo que dejan abierto.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | El «Layout» de la ficha es `AppShell`, en `App.jsx`. Tiene menú lateral (`lg:static`), cabecera y `<main>` con las rutas; la pantalla ancha se decide con `usePantallaAncha` (64 rem) | El panel y el botón flotante cuelgan de `AppShell`, fuera de `<Routes>`: así sobreviven al cambio de ruta (CA 1). El estado de la conversación vive en un proveedor dentro de `AppShell`, no en el panel |
| C2 | `apiFetch` (`client.js`) hace `res.json()` de toda respuesta, así que no sirve para un `text/event-stream`. Lleva el token con `getTokens()` y, ante un 401, `tryRefresh()` (que no se exporta) | El cliente de streaming es un módulo nuevo (`src/api/chat.js`), con `fetch`, `ReadableStream` y `AbortController`. Reutiliza `getTokens`/`setTokens`/`clearTokens`. Cómo renueva el token: decisión Y2 |
| C3 | `useConsulta` es de petición única con reintento; sus 3 avisos de ESLint son deuda | No se toca. Se crea un hook propio `useChat` con la máquina de estados de la ficha |
| C4 | El token de acceso dura 30 min y el Core API responde 401 **antes de abrir el flujo** si le quedan menos de 120 s | El cliente debe renovar y reintentar una vez; si no, una conversación larga se corta con «sesión expirada» sin que el usuario haya hecho nada |
| C5 | La ficha pide estado «en cola». No hay evento de cola: un segundo flujo recibe 429 con `Retry-After` (X3 de INV-36) | «En cola» se muestra como «el agente está atendiendo otra consulta» con reintento automático tras `Retry-After` o botón manual |
| C6 | Mientras el agente verifica no llega ningún `token`: solo `tool`, `data` y `: ping`. En frío puede pasar de 60 s sin texto | Estados: *conectando* (hasta `meta`), *consultando* (con la `etiqueta` de cada `tool`; `lenta` → «calculando recomendaciones… puede tardar hasta 40 s») y *redactando* (llegan `token`). El lector ignora `: ping` |
| C7 | Los `filas` de `data` llegan ya formateados en es-CO, como texto (`"1.092"`), y `columnas` trae `tipo` | La tabla muestra el valor tal cual y alinea a la derecha las columnas `numero`. No se usa `formato.js` sobre ellas |
| C8 | «Con unidades»: en las herramientas de inventario las celdas ya traen la unidad (`"-3 unidades"`, `"-27,6 d"`) | Las unidades vienen del dato, no del texto del modelo (CA 4). No se agregan ni se calculan |
| C9 | `done` trae `respaldo`, `fidelidad`, `sugerencias` (hasta 3) y `turnos_recortados`; con `respaldo` el texto empieza con «No pude redactar una respuesta verificada…» | El mensaje de respaldo se marca de forma visible. Las sugerencias son botones que envían su texto como pregunta; llegan vacías tras un respaldo o un 403 |
| C10 | El 403 de una herramienta llega como `tool` con `codigo: 403`, no como error HTTP | CA 5: el estado de error por código se lee del `tool` (y del `error` del flujo), no solo del HTTP |
| C11 | Si el agente corta sin `done` ni `error`, el Core API cierra el flujo sin agregar eventos (X5-b de INV-36 no se aprobó) | Un flujo que termina sin `done` es un corte: el mensaje queda marcado como incompleto y con botón de reintentar |
| C12 | El texto del agente es Markdown (negritas y listas numeradas). El front no tiene ninguna librería de Markdown | Se muestra como Markdown seguro, sin HTML crudo (CA 3). Cómo: decisión Y1 |
| C13 | Los límites del Core API son 13 mensajes (6 turnos y la pregunta), 2.000 caracteres por mensaje y 16.000 en total; sobrepasarlos da 422 | El campo de texto limita a 2.000 caracteres con contador. Al llegar a los 6 turnos: decisión Y4 |
| C14 | Las 61 preguntas del conjunto v1 tienen `rol`, pero no están pensadas como botones (son largas, o piden contexto como `sucursal_usuario`) y están fuera del front (`nlp_agent/evaluacion`) | No se lee ese archivo desde el navegador: se curan unas pocas por rol en un módulo del front. Decisión Y5 |
| C15 | Vite sirve la app con un proxy a `/api` que espera 130 s; Nginx lleva `/api/chat/` sin buffer ni gzip | Se prueba con `npm run dev` y con el 8080. En jsdom no hay streaming real: las pruebas usan un `ReadableStream` simulado con fragmentos partidos a mitad de evento |
| C16 | `coverage.include` de `vite.config.js` lista los archivos uno por uno en `pages/` y por carpeta en el resto (`src/api/**`, `src/components/**`, `src/hooks/**`, `src/utils/**`) | Los archivos nuevos de `api/`, `hooks/`, `components/` y `utils/` entran solos; un módulo en otra carpeta se agrega a mano. Umbral 80 % |
| C17 | El título de Jira dice PWA y la aplicación no lo es (A3) | Fuera de INV-35: no hay *service worker* ni instalación. La nota se deja en la documentación de cierre |
| C19 | El chat se llama **Vera**. El paquete de identidad v2 trae paleta (solo colores de InventAI/o), DM Sans, ícono, avatar y la animación «pensando» (3 barras que suben y bajan) | Todo texto visible al usuario habla de Vera, no de «el agente» ni «el asistente». La sección 4.1 baja la identidad a componentes. La API y el código interno siguen llamándose «agente»/«chat» |
| C18 | El panel no debe pesar en el bundle de arranque (riesgo de la ficha) | El panel y su Markdown se cargan con `React.lazy` al abrir el botón por primera vez; el botón flotante y el proveedor son livianos |

## 3. Decisiones (formulario del 24-oct)

| # | Tema | Propuesta | Alternativa |
| --- | --- | --- | --- |
| Y1 | Markdown seguro | Un renderizador propio y mínimo (párrafos, **negritas**, listas con viñetas y numeradas) que produce nodos de React: sin HTML crudo por construcción y sin dependencia nueva | `react-markdown` (más completo, ~40 kB, una dependencia más que revisar con `npm audit` y Dependabot) |
| Y2 | Renovar el token en el flujo | Exportar `tryRefresh` desde `client.js` (cambio de una palabra, sin tocar su comportamiento) y llamarlo desde `chat.js` ante un 401 | Duplicar la renovación en `chat.js` (no se toca `client.js`, pero hay dos rutas que rotan el mismo refresh token) |
| Y3 | Distribución en pantalla ancha | ~~Panel lateral acoplado a la derecha (≥ `lg`) que **empuja** el contenido~~ (elegida el 24-oct). **Revisada el 27-oct por el usuario:** desde `sm` (40 rem), ventana flotante abajo a la derecha que no angosta la página y se puede **maximizar**; en el celular, pantalla completa | Panel superpuesto sobre la página, sin mover el contenido |
| Y4 | Límite de longitud (CA 9) | Ventana: el panel guarda hasta 40 mensajes y envía al agente los últimos 13; se avisa «el agente recuerda solo los últimos 6 turnos» | Bloquear al llegar a 6 turnos y pedir «Nueva conversación» |
| Y5 | Preguntas rápidas (CA 7) | 4 por rol, curadas a mano a partir del v1 y ubicadas en `src/utils/preguntasRapidas.js`; las de seguimiento salen de `done.sugerencias` | Tomar al azar del v1 completo (dependería de que cada pregunta sirva sola) |

## 4. Diseño propuesto

```
AppShell
 ├─ ChatProvider        estado: mensajes, abierto, fase; useChat(); AbortController
 ├─ <main> + <Routes>   sin cambios
 └─ BotonChat / PanelChat (lazy)
      ├─ ListaMensajes    aria-live="polite"; MensajeUsuario / MensajeAgente
      │    ├─ Markdown          texto del agente
      │    ├─ TablaDatos        eventos `data`
      │    └─ HerramientasConsultadas   etiquetas + fecha_dato (CA 6)
      ├─ EstadoChat       conectando · en espera · consultando · redactando · error por código
      ├─ Sugerencias      botones de done.sugerencias y preguntas rápidas
      └─ Compositor       Enter envía, Mayús+Enter salta de línea, detener / reintentar
```

Máquina de estados de `useChat`: `reposo → enviando → transmitiendo → reposo | error`. `error` guarda el código (`401`, `403`, `429`, `5xx`, `tiempo_agotado`, `llm_no_disponible`…) y si es reintentable.

Archivos nuevos: `src/api/chat.js` (lector de SSE y petición), `src/hooks/useChat.js`, `src/components/chat/*`, `src/utils/preguntasRapidas.js` y sus pruebas.

### 4.1 Identidad de Vera

- **Ícono** (burbuja con tres barras, la alta en teal sale del borde): botón flotante y cabecera del panel. Sobre fondo navy, la versión «sobre oscuro». Hover del botón: `brand-navydark`.
- **Avatar** circular junto a cada mensaje de Vera (versión clara sobre fondo blanco).
- **«Pensando»:** las tres barras escalan desde la base con 150 ms de desfase mientras Vera consulta o verifica; con `prefers-reduced-motion` quedan quietas. Reemplaza al *spinner* y acompaña, no sustituye, al texto del estado (CA 5).
- **Colores:** mensajes del usuario en `brand-blue` con texto blanco; mensajes de Vera en `#EFF6FF` con texto `#334155`; datos clave en navy y negrita; el teal **nunca** como texto sobre blanco ni para alertas (en la app el ámbar es alerta de inventario).
- **Textos fijos:** título «Vera», lema «Pregúntale a tu inventario», campo «Escribe tu pregunta…», firma «Vera, la asistente de InventAI/o». La esquina recta de cada burbuja apunta a quien habla.
- **Archivos:** el ícono y los avatares se dibujan como componente de React (`Vera.jsx`, SVG en línea) para animar las barras; el paquete `vera-v2/svg` queda de referencia, sin versionarse completo.

## 5. Criterios de aceptación

Son los 11 de la ficha, con estas precisiones tomadas de la sección 2:

1. **Panel global de Vera** en `AppShell`, para los 3 roles, persistente entre rutas (C1).
2. **Cliente de streaming** en `src/api/chat.js`, con detener y reintentar (C2, C4, C11).
3. **Mensajes diferenciados** y Markdown seguro (C12).
4. **Eventos `data`** como tabla, con los valores y unidades del dato (C7, C8).
5. **Estados** conectando, en espera, consultando, calculando recomendaciones, y error por código, incluido el 403 del `tool` (C5, C6, C10).
6. **Herramientas consultadas y fecha del dato** en cada respuesta (`etiqueta`, `fecha_dato`).
7. **Preguntas rápidas** por rol y de seguimiento (C9, C14). Es (S): la primera en recortarse.
8. **Accesibilidad:** foco al abrir y al cerrar, `aria-live`, Enter y Mayús+Enter, contraste.
9. **Conversación solo en memoria**, con «Nueva conversación» y límite (C13).
10. **Pruebas de Vitest** del lector de SSE con fragmentos partidos, el hook y los componentes; `coverage.include`, matriz de `frontend/README.md` y bloque en `docs/INV-26-pruebas-pantallas.md`.
11. **Persistencia del historial:** (C), fuera de esta historia (INV-37).

## 6. Pruebas

- **Vitest:** `ReadableStream` simulado; casos de lector (evento partido a mitad, varios eventos en un fragmento, `: ping`, flujo sin `done`); el hook (reposo, enviando, transmitiendo, error, detener, reintentar, 401 con renovación, 429); los componentes por rol.
- **De punta a punta:** el stack del 8080 y los 5 usuarios de prueba, con una pregunta por rol y el caso 403 (un `admin_sucursal` preguntando por otra sucursal). Responsive: pantalla ancha y móvil.

## 7. Fuera de alcance

Persistencia (INV-37), PWA (A3), el agente v3 y los holdouts.

## 8. Mejoras del 27-oct (fuera de Jira, dentro del merge)

El 27-oct, después de la revisión de la ventana flotante (Y3), el usuario aprobó estas mejoras. **No se registran en Jira**, pero entran en el mismo merge de INV-35, con sus pruebas y sus casos en la guía de pantallas. Ninguna cambia el contrato v1.1 con el agente. M7 entra solo si queda tiempo antes del congelamiento del 30-oct.

| # | Mejora | Por qué | Cómo se verifica |
| --- | --- | --- | --- |
| M1 | **Validar las 12 preguntas rápidas** contra el agente real, cada una con un usuario de su rol, y reemplazar las que fallen por otras del conjunto v1 | «Dame un reporte general de las alertas por nivel», la primera que ve el gerente, terminó en respuesta de respaldo en todas las corridas del 27-oct | Una corrida con el stack real: las 12 con `respaldo: false`, sin `error` y con al menos una herramienta. Los reemplazos quedan anotados en `INV-35-chat.md` |
| M2 | **Aviso de demora:** si pasan 10 s sin eventos (el `: ping` no cuenta) y todavía no hay texto, «Está tardando más de lo normal: la primera pregunta después de iniciar el modelo puede tardar hasta un minuto.» Desaparece con el siguiente evento | En frío hubo 64 s sin eventos (H1 de INV-36); hoy solo se ven las barras y puede parecer que Vera se colgó | Vitest con relojes falsos: aparece a los 10 s, se va con un evento, no aparece cuando ya hay texto ni junto al aviso de la herramienta lenta |
| M3 | **Disponibilidad al abrir:** `GET /api/chat/health` cada vez que se abre Vera. Con 503, 502, 504 o sin conexión, un aviso «Vera no está disponible» con el motivo y «Volver a comprobar», y el envío deshabilitado. Cualquier otra respuesta no bloquea | Hoy la caída del agente se descubre al preguntar. El endpoint queda consumido en la matriz | Vitest: listo, 503 con cada `motivo`, sin conexión y recuperación con «Volver a comprobar». En vivo: K-11 con el agente detenido |
| M4 | **Descargar cada tabla de Vera a CSV**, con el formato de Excel en Colombia de `csv.js`: las columnas `numero`, las `cantidad` de una sola unidad (el título lleva la unidad) y los montos «$ …» salen como números; lo demás, como texto. Solo las filas que llegaron. De paso, las columnas `cantidad` se alinean a la derecha como las `numero` | Llevar a Excel lo que respondió Vera sin copiarlo a mano | Vitest de la conversión (miles, decimales, unidades mezcladas, montos, vacíos) y del botón. En vivo: abrir el archivo en Excel |
| M5 | **Tiempo de respuesta** al pie: «Respondió en 3,0 s», de `done.ms_total` | Evidencia de latencia a la vista para la demo y el dossier | Vitest: con `ms_total` y sin `done` (corte) |
| M6 | **Título de pestaña por página:** «Alertas · InventAI/o»; en el login, «Iniciar sesión · InventAI/o» | Hoy todas las pestañas dicen «InventAI/o» (WCAG 2.4.2) | Vitest: el título cambia al navegar |
| M7 | (Si hay tiempo) **«Preguntar a Vera» desde Alertas y Recomendaciones:** un botón en cada tarjeta o fila (el ícono de Vera, sin texto, con la pregunta en el *tooltip*) que abre Vera con la pregunta armada sobre ese producto y esa sucursal. **Alcance reducido el 27-oct a Alertas**, por la validación: las preguntas por producto de traslados y compras daban respuestas falsas o 403 (H13 de `INV-35-chat.md`) | Une la aplicación con Vera: la demo pasa de una alerta a su explicación | Las preguntas se validan contra el agente como en M1. Vitest de la página y repetir los bloques E y J de la guía |
| M8 | README: la nota que dice que `/api/chat/` es de INV-36 | Quedó desactualizada | Lectura |

**Segunda tanda** (aprobada el 27-oct, después del commit de M1–M8; mismas reglas: fuera de Jira, dentro del merge):

| # | Mejora | Por qué | Cómo se verifica |
| --- | --- | --- | --- |
| M9 | **Copiar la respuesta:** botón «Copiar» al pie de cada respuesta terminada; copia el texto sin las marcas de Markdown y dice «Copiada» unos segundos. Si el navegador no permite el portapapeles, no se muestra | Llevar la respuesta a un correo o un informe sin seleccionarla a mano | Vitest con el portapapeles simulado; en vivo, pegarla |
| M10 | **Campo que crece** con el texto, de 2 a 6 líneas; después se desplaza | Las preguntas largas no caben en dos líneas | Vitest de la altura; en vivo |
| M11 | **Atajo Alt+V:** con Vera cerrada, la abre; abierta y con el foco afuera, lo lleva al campo; con el foco adentro, la cierra. El botón lo anuncia (`aria-keyshortcuts` y tooltip) | Abrir Vera sin el mouse desde cualquier página | Vitest de los tres casos |
| M12 | **Preguntas rápidas según la página:** en Alertas, Inventario, Recomendaciones, Predicciones y Reportes, tres preguntas de esa página (unas para quien ve toda la red y otras para el administrador de sucursal); en el Dashboard, las del rol. Se validan contra el agente como en M1 | Que lo primero que ofrece Vera tenga que ver con lo que el usuario está mirando | Corrida con el stack real (todas sin respaldo ni error, con herramienta); Vitest por página y rol |
| M13 | **«Saltar al contenido»:** el primer elemento al navegar con Tab, visible solo con el foco; lleva el foco al contenido de la página | Quien usa el teclado no tiene que recorrer el menú en cada página (WCAG 2.4.1) | Vitest; en vivo con Tab |

**No entran ahora** (decisión del 27-oct): persistir la conversación (INV-37; la ficha la pide solo en memoria), quitar desde el frontend el «Datos al…» que repite el modelo (le corresponde al prompt del agente v3), el pulgar arriba o abajo por respuesta (no hay dónde guardarlo sin backend), mandarle al agente la página actual (cambia el contrato) y usar el encabezado vacío del escritorio (toca todas las páginas).
