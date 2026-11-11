# INV-68 · Ajustes previos a las pruebas con usuarios · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-68 «Ajustes previos a las pruebas con usuarios» · 5 SP · Sprint 7 · Release 3 · límite 20-nov |
| Depende de | INV-34 (staging con HTTPS) para los criterios 4 y 5. Los criterios 1, 2, 3 y 6 se hacen antes, en local |
| Alimenta a | INV-38 (pruebas con usuarios, Sprint 8) |
| Rama | `feature/INV-68-ajustes-pruebas`, desde `develop` (`f8caebc`), en el worktree `~/InventaIO-wt/INV-68` |

Revisión del 10 de noviembre de 2026 contra `develop` y el stack local del 8080, con Playwright en 360 y 768 px. Las decisiones U1 a U4 las tomó el usuario ese día en un formulario; U5 es técnica.

## 1. Historia de Jira

> Como gerente o administrador que va a probar la aplicación, quiero que las pantallas funcionen bien en el celular y en la nube, para que las pruebas midan su utilidad y no tropiecen con detalles ya conocidos.

Cuatro criterios (M) y dos (S). Fuera de alcance: PWA (INV-70), rediseño de pantallas y las pruebas con usuarios en sí (INV-38).

## 2. Contraste con lo ya construido

| # | Hallazgo (10-nov) | Consecuencia |
| --- | --- | --- |
| C1 | En 360 px ninguna de las seis páginas se desborda: las tablas se deslizan dentro de su caja. En 768 px, tampoco | El CA 6 parte en verde. Se vuelve a medir al final |
| C2 | Inventario en 360 px: la tabla tiene un ancho mínimo de 820 px; se ven Producto, Categoría y Sucursal, mientras Stock y Estado quedan fuera de la pantalla | CA 1 (U1) |
| C3 | Recomendaciones en 360 px: en la tabla de líneas de compra, Stock también queda fuera | No está en la ficha (U3) |
| C4 | La barra superior está vacía para el gerente y el administrador de bodega; en el celular solo tiene el botón del menú. El administrador de sucursal ve su sucursal | CA 3 (U2) |
| C5 | `Login.jsx` dice «v1.0» en duro; `package.json` dice 2.0.0 y `/api/health` no da versión. INV-34 (CA 6) pide la versión y el commit en la barra y en el login | U2 resuelve la parte de la interfaz; a INV-34 le queda pasar el commit y `/api/health` |
| C6 | `index.html` carga DM Sans (400 a 700) desde Google Fonts | CA 2 (U5) |
| C7 | `useMedia` (Vera, INV-35) elige la vista por media query y, sin `matchMedia` (jsdom), toma la pantalla como ancha | Las tarjetas se eligen con él: en las pruebas sigue la tabla, y las tarjetas se prueban simulando un celular |
| C8 | La CSP de Nginx solo tiene `frame-ancestors 'none'` (INV-66, H9). Fuera de los archivos propios, la aplicación solo usa una imagen `data:` (el fondo del login) y descargas `blob:` (el CSV, que es una navegación y la CSP no limita). No hay scripts ni estilos en línea ni CSS en JS | Con las fuentes alojadas, cabe una CSP con `'self'` y `data:` para imágenes (U4) |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| U1 | Inventario: tarjetas por debajo de 48 rem (768 px) y tabla desde ahí. Cada tarjeta lleva el nombre, la sucursal y la categoría, el stock en grande con su estado, y la bodega y la cobertura. Toda la tarjeta es un botón que abre el detalle, como el nombre en la tabla | Usuario, 10-nov |
| U2 | Barra superior con el nombre de la página (el `label` de `RUTAS`), que sigue visible al desplazar, y la versión a la derecha. La versión sale de `package.json` al compilar y el commit, de `VITE_COMMIT`, que recibe la imagen web como `ARG` (INV-34 le pasa el valor). El login usa la misma constante | Usuario, 10-nov |
| U3 | Recomendaciones queda fuera: se anota y se revisa con lo que digan las pruebas con usuarios (INV-38) | Usuario, 10-nov |
| U4 | CSP completa en `frontend/nginx/cabeceras-seguridad.conf`, verificada con Playwright en las seis páginas y en Vera, sin violaciones | Usuario, 10-nov |
| U5 | Fuentes con `@fontsource-variable/dm-sans`: un archivo para los pesos 400 a 700, sin dominios externos | Técnica (C6) |

## 4. Interfaz

### 4.1 CSP (U4)

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self';
connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

Reemplaza la línea de `frame-ancestors` de INV-66: dos cabeceras CSP se aplicarían a la vez. Los estilos que pone React con la prop `style` pasan, porque los asigna por el DOM (`element.style`) y no como atributo en el HTML. En desarrollo (Vite, 5173) no hay CSP: no pasa por Nginx.

### 4.2 Versión (U2)

`src/version.js` exporta `VERSION_TEXTO`: `v2.0.0`, o `v2.0.0 · a1b2c3d` cuando hay commit. `vite.config.js` define `__APP_VERSION__` con la versión de `package.json`, y `frontend/Dockerfile` recibe `ARG VITE_COMMIT`.

## 5. Criterios de aceptación

| CA | Cómo se cumple | Cuándo |
| --- | --- | --- |
| 1 (M) Stock en el celular | U1 | Ahora |
| 2 (M) Fuentes alojadas | U5 | Ahora |
| 3 (M) Barra superior útil | U2 | Ahora |
| 4 (M) Vera en staging con HTTPS | Copiar, streaming y tiempos | Con INV-34 (19-nov) |
| 5 (S) Guion y consentimiento | Para INV-38 | Con INV-34 |
| 6 (S) Revisión en 360 y 768 px | Playwright sobre las seis páginas | Ahora en local y repetida en staging |

## 6. Casos de prueba

| # | Caso | Dónde |
| --- | --- | --- |
| P1 | Con un celular simulado, Inventario muestra tarjetas con el stock y el estado, y no muestra la tabla | Vitest |
| P2 | Tocar una tarjeta abre el detalle de ese producto y esa sucursal | Vitest |
| P3 | En pantalla ancha sigue la tabla (las pruebas actuales) | Vitest |
| P4 | La barra muestra el nombre de la página y la versión; el administrador de sucursal, además, su sucursal | Vitest |
| P5 | El login muestra la versión de `package.json`, no «v1.0» | Vitest |
| P6 | Sin peticiones a dominios externos al cargar las páginas | Playwright |
| P7 | Ninguna violación de CSP en las seis páginas, en el login, al abrir Vera y al hacerle una pregunta | Playwright contra la imagen web de la rama |
| P8 | En 360 px, Stock visible en Inventario; ninguna página se desborda en 360 ni en 768 px | Playwright |

## 7. Ruta

1. Fuentes (U5) y versión (U2) con la barra y el login.
2. Tarjetas de Inventario (U1).
3. CSP (U4) y la imagen web de la rama sobre la red del stack local.
4. Vitest, ESLint y cobertura; Playwright P6 a P8.
5. Pull Request a `develop`. Los criterios 4 y 5 quedan para después del staging (INV-34).

## 8. Fuera de alcance y riesgos

- Recomendaciones en el celular (U3), la PWA (INV-70), el commit en `/api/health` (INV-34).
- **Riesgo:** una librería que agregue estilos en línea en el futuro rompería la CSP. Playwright lo detecta (P7) y el navegador lo muestra en la consola.
- **Riesgo:** los criterios 4 y 5 dependen del staging del 19-nov.

## 9. Verificación (10-nov, en local)

| Prueba | Resultado |
| --- | --- |
| Vitest (P1 a P5) | 320 pruebas (7 nuevas); cobertura de líneas del 98,98 % (mínimo 80 %). ESLint sin errores, con los 3 avisos que ya estaban en `develop` |
| `npm audit` y build | Sin vulnerabilidades. DM Sans queda en `dist/assets` (37 KB más 18 KB con latin-ext) y no queda ninguna referencia a Google Fonts |
| P6 a P8, con la imagen web de la rama en la red del stack local y Playwright en 360, 768 y 1280 px | Ninguna violación de CSP en el login, en las seis páginas ni en Vera (respuesta completa por streaming, con tabla y CSV); ninguna petición a otros dominios; ninguna página se desborda; en 360 px, Inventario muestra 15 tarjetas con el stock a la vista, y desde 768 px, la tabla; la barra dice la página y `v2.0.0 · <commit>`; la fuente que se aplica es «DM Sans Variable» |
| `scripts/probar_nginx_streaming.sh` | 4/4 con la CSP nueva |

Las capturas quedan fuera del repositorio porque muestran datos del negocio.
