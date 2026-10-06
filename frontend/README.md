# Frontend de InventAI/o

React 18, React Router 7, Vite 8 y Tailwind 4, contra el Core API (puerto
8000). Este documento es la guía para trabajar sobre la base que dejó el fix de
INV-26 (`docs/INV-26-fix.md`): las convenciones, cómo agregar una vista y la
matriz de qué endpoint usa cada pantalla. Cada historia que consuma o agregue
un endpoint actualiza la matriz.

## Stack

| Paquete | Versión | Notas |
| --- | --- | --- |
| `react`, `react-dom` | 18.3 | |
| `react-router` | 7 | Se importa de `react-router` (ya no de `react-router-dom`) |
| `vite` | 8 | Empaqueta con Rolldown; `@vitejs/plugin-react` 6 |
| `tailwindcss` | 4 | Con `@tailwindcss/vite`. La configuración está en `src/index.css` (`@theme`): no hay `tailwind.config.js` ni `postcss.config.js` |
| `vitest`, `@vitest/coverage-v8` | 5 | Con jsdom 26 y Testing Library 16. Los `console.log` de las pruebas que pasan no se muestran: `npx vitest run --silent=false` |
| `recharts` | 2 | Solo en Dashboard, Reportes y Predicciones; va en su propio archivo (ver "Cómo agregar una vista") |

`src/index.css` tiene, además del tema, un bloque de compatibilidad con
Tailwind 3: color de borde gris por defecto, cursor de mano en los botones y
placeholder gris. Tailwind 4 usa su paleta en OKLCH: los rojos y verdes de la
librería son algo más vivos que en Tailwind 3; los colores de la marca
(`brand-*`) no cambian.

## Correr y probar

Requiere Node 22.12 o superior (`engines` en `package.json`; `.nvmrc` con 22),
que pide Vitest 5. npm avisa con `EBADENGINE` si la versión no alcanza, y con
Node 18 Vite no arranca (`SyntaxError: Identifier 'addon' has already been
declared`).

El ambiente es Linux, como el servidor y el CI: en Windows, Ubuntu en WSL2 con
el repositorio en `~/InventaIO` (ver `docs/AMBIENTE-DESARROLLO.md`). `apt`
instala Node 18; el 22 se instala con nvm:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 22     # en frontend/, `nvm use` toma la versión de .nvmrc
```

**`node_modules` es del sistema donde se instaló.** Vite 8 (Rolldown) y
Tailwind 4 (`lightningcss`, `oxide`) traen binarios nativos: se instala con
`npm ci` en Linux y no se copia desde Windows. Por eso el repositorio no va en
`/mnt/c`: ahí también serían lentos los montajes de Docker y Vite no vería los
cambios. Chrome en Windows abre http://localhost:5173 servido desde WSL sin
configuración extra.

Con el Core API arriba (`docker compose up -d ml-service api`; `--build` solo si
cambió un `requirements.txt` o un `Dockerfile`):

```bash
npm ci
npm run dev        # http://localhost:5173; /api va al 8000 con 130 s de espera
npm run test       # pruebas (Vitest + Testing Library)
npm run test:cov   # con cobertura; falla por debajo del 80 %
npm run build
npm audit          # debe dar 0 vulnerabilidades; el CI falla con altas en producción
```

Usuarios de prueba: `gerente@inventaio.co`, `admin.principal@inventaio.co`,
`admin.norte@inventaio.co`, `admin.sur@inventaio.co` y `bodega@inventaio.co`,
con clave `admin123`. Los crea o los restablece (por ejemplo, después de probar
el cambio de contraseña) el seed del Core API:

```bash
docker exec inventaio-api python -m scripts.seed_usuarios
```

## Estructura

| Carpeta | Qué hay |
| --- | --- |
| `src/api/` | `client.js` (todas las llamadas al Core API, `ApiError`) y `AuthContext.jsx` (sesión) |
| `src/hooks/` | `useConsulta` (consultas desde las páginas), `useSucursal` (ubicación según el rol), `useSucursales` (lista de ubicaciones, una sola carga) |
| `src/components/` | Piezas compartidas: `SucursalSelector` (con `incluirBodega` y `opcionVacia`), `Cargando`, `MensajeError`, `EstadoConsulta`, `GuardaRol`, `DistintivoBodega`, `DetalleInventario`, `CambiarPassword` |
| `src/utils/` | `formato.js` (números, conteos en singular o plural, cantidades por unidad, solas o con su unidad, con la misma regla que los textos del Core API, moneda, fechas), `graficas.js` (puntos de los meses aislados, barras de Predicciones), `etiquetas.js` (nombres de alertas, estados, ubicaciones, unidad de venta, urgencias de las recomendaciones, riesgo y ramas del modelo; `etiquetaDe` para un valor sin etiqueta), `riesgo.js` (riesgo según el pronóstico) y `periodos.js` (atajos de período de Reportes) |
| `src/pages/` | Una página por ruta: Dashboard, Inventario, Alertas, Reportes, Predicciones y Login |
| `src/rutas.js` | La lista `RUTAS`: alimenta el menú y las rutas; cada página se descarga al entrar a ella |
| `src/test/` | `setup.js` y `utils.jsx` (`renderConUsuario`, `simularApi`, `USUARIOS`) |

## Convenciones

1. **Toda función de `client.js` tiene una pantalla que la usa y sus pruebas.** Una función nueva entra con la vista que la consume. La excepción son las que dejó el fix para INV-27 (marcadas en la matriz).
2. **Ningún dato de la bodega va fijo en el código.** Categorías, ubicaciones y tipos se piden al Core API.
3. **Una sola implementación de cada cosa:**
   - consultas con `useConsulta`;
   - errores con `ApiError` y `MensajeError` (o `EstadoConsulta`);
   - números y fechas con `formato.js`;
   - nombres con `etiquetas.js`;
   - ubicaciones con `useSucursales` y `useSucursal`;
   - menú y rutas con `RUTAS`.
4. **Identificadores.** El pronóstico y el histórico van por `id_producto` e `id_sucursal`; las recomendaciones, por nombre de sucursal (`sucursalNombre` de `useSucursal`).
5. **La Bodega Central.** Se muestra con `nombreUbicacion` ("Bodega Central") y `DistintivoBodega`. No vende: no se le piden ventas.
6. **Todo endpoint aparece en la matriz** con su pantalla o su destino. Una funcionalidad nueva o que haga falta se reporta en la matriz y en su historia antes de implementarse.
7. **Lo nuevo o tocado queda con pruebas**, dentro de la cobertura de `vite.config.js`.

## Cómo agregar una vista

1. **La función en `client.js`**, con el último argumento `op` pasado a `apiFetch`, y su prueba en `client.test.js`. Para ML, `conTimeoutML(op)` (130 s).
2. **La página en `src/pages/`**, con `useConsulta` y `EstadoConsulta`:

   ```jsx
   const { sucursalId, sucursalNombre, showSelector, rawSucursalId, setSucursalId } = useSucursal()
   const compras = useConsulta(
     op => getRecomendacionesCompras({ sucursal: sucursalNombre }, op),   // pasar op a client.js
     [sucursalNombre],
   )
   return (
     <EstadoConsulta consulta={compras} aviso="La primera consulta tarda hasta 40 s">
       {datos => <Tabla lineas={datos.compras} />}
     </EstadoConsulta>
   )
   ```

   `useConsulta(fn, deps, { timeoutMs, activo })`: `fn` recibe `{ signal, timeoutMs }`; con `activo: false` no consulta.
3. **La entrada en `RUTAS`** (`src/rutas.js`) con su `path`, `label`, `icon`, `roles` y `pagina`. El menú y la guarda por rol salen de ahí. La página se declara con `lazy(() => import('./pages/Predicciones'))`, como las demás: así no viaja con el login y el build no pasa de 500 kB por archivo. `App.jsx` muestra `Cargando` mientras se descarga.
4. **Las pruebas de la página**, con `renderConUsuario` y `simularApi`:

   ```jsx
   simularApi({ 'POST /api/ml/predict': { status: 404, body: { detail: 'historia insuficiente' } } })
   renderConUsuario(<Predicciones />, USUARIOS.adminPrincipal)
   expect(await screen.findByRole('alert')).toHaveTextContent('historia insuficiente')
   ```

   Si `App.test.jsx` navega a la página nueva, se importa al inicio del archivo (`import './pages/Predicciones'`), como Dashboard y Alertas: con la suite en paralelo, la primera descarga puede pasar el segundo de espera de `findBy`.
5. **La página en la cobertura** (`test.coverage.include` de `vite.config.js`).
6. **La fila de cada endpoint en la matriz**, abajo.

## Matriz endpoint → pantalla → historia

Los 28 endpoints del Core API al cierre de INV-26: 23 tienen pantalla, 2
tienen su función lista para INV-27, los 2 de proveedores no se consumen por
decisión (proveedores simulados) y el health es de infraestructura. Ninguno
queda sin destino.

| Endpoint | Función de `client.js` | Pantalla | Dónde |
| --- | --- | --- | --- |
| `POST /api/auth/login` | `login` | Login | Release 1 |
| `POST /api/auth/refresh` | interna de `apiFetch` | Todas | Release 1 |
| `POST /api/auth/logout` | `logout` | Menú del usuario | Release 1 |
| `GET /api/auth/me` | `getProfile` | Sesión | Fix de INV-26 (A2.6) |
| `PATCH /api/auth/password` | `cambiarPassword` | Menú del usuario | Fix de INV-26 (A3.7) |
| `GET /api/consulta/productos` | `getProductos` | Predicciones (buscador) | INV-26 (busca también por código, V11) |
| `GET /api/consulta/productos/{id}` | `getProducto` | Detalle de inventario | Fix de INV-26 (A3.6) |
| `GET /api/consulta/productos/{id}/ventas` | `getVentasProducto` | Predicciones (8 ventanas del gráfico) | INV-26 |
| `GET /api/consulta/sucursales` | `getSucursales` (vía `useSucursales`) | Selector de todas las páginas | Fix de INV-26 (A2.5) |
| `GET /api/consulta/proveedores` | — | — | No se consume: proveedores simulados |
| `GET /api/consulta/proveedores/{id}` | — | — | No se consume: proveedores simulados |
| `GET /api/consulta/categorias` | `getCategorias` | Inventario; Recomendaciones | Fix de INV-26 (A3.4); INV-27 |
| `GET /api/consulta/inventario` | `getInventario` | Inventario | Fix de INV-26 (A3.4; `unidad` y `semaforo=inconsistencia` en A8) |
| `GET /api/consulta/inventario/detalle` | `getInventarioDetalle` | Detalle de inventario; Predicciones (stock y cobertura) | Fix de INV-26 (A3.6); INV-26 |
| `GET /api/consulta/inventario/resumen` | `getInventarioResumen` | Dashboard | Fix de INV-26 (A3.2; conteo de `inconsistencia` en A8) |
| `GET /api/consulta/inventario/valorizado` | `getValorizado` | Reportes | Fix de INV-26 (A9) |
| `GET /api/alertas` | `getAlertas` | Alertas | Fix de INV-26 (A3.5; páginas de 50 desde la API en A8) |
| `GET /api/alertas/resumen` | `getAlertasResumen` | Dashboard, Alertas | Fix de INV-26 (A3.2, A3.5) |
| `GET /api/reportes/kpis` | `getKPIs` | Dashboard | Fix de INV-26 (A3.2; "En riesgo" = bajo + crítico del semáforo en A8, K9) |
| `GET /api/reportes/ventas` | `getVentas` | Reportes | Fix de INV-26 (A9) |
| `GET /api/reportes/ventas/comparativa` | `getComparativa` | Reportes | Fix de INV-26 (A9) |
| `GET /api/reportes/ventas/top-productos` | `getTopProductos` | Dashboard | Fix de INV-26 (A3.2) |
| `GET /api/reportes/tendencias` | `getVentasTendencia` | Dashboard; Reportes | Fix de INV-26 (A3.2; con categoría, agrupación y una serie por sucursal en A9) |
| `GET /api/reportes/distribucion-categorias` | `getDistribucionCategorias` | Reportes | Fix de INV-26 (A9) |
| `GET /api/ml/recomendaciones/compras` | `getRecomendacionesCompras` | Recomendaciones | INV-27 (función lista) |
| `GET /api/ml/recomendaciones/transferencias` | `getRecomendacionesTransferencias` | Recomendaciones | INV-27 (función lista) |
| `POST /api/ml/predict` | `predecir` | Predicciones | INV-26 |
| `GET /api/health` | — | — | Infraestructura, sin pantalla |
