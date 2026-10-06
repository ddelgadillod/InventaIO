# INV-26 · Fix previo · Pruebas de pantallas

Guía para validar en el navegador las pantallas que adaptó o agregó el fix de
INV-26: Login y menú, Dashboard, Inventario, detalle de inventario, Alertas,
Reportes y cambio de contraseña. El bloque H cubre la vista de predicciones de
INV-26 ([`INV-26-predicciones.md`](INV-26-predicciones.md)). Está escrita para que la siga una persona o un agente que maneje
el navegador (por ejemplo, Cowork): cada caso dice qué hacer, con qué
usuario y qué debe verse exactamente.

Las cifras salen de la bodega real (foto al 2025-12-31) y se verificaron
contra el Core API. Las pruebas automáticas (pytest y Vitest) están en
[`INV-26-fix.md`](INV-26-fix.md); esta guía cubre lo que solo se ve en pantalla.

## 1. Preparación

La hace una persona antes de empezar, en la terminal de Ubuntu (WSL) y desde la raíz del repositorio (`~/InventaIO`, ver `docs/AMBIENTE-DESARROLLO.md`):

1. Servicios arriba: `docker compose up -d ml-service api`. El contenedor `api` monta el código y se recarga solo; `--build` solo hace falta si cambió un `requirements.txt` o un `Dockerfile`. Si `docker compose ps` ya los muestra corriendo, este paso sobra.
2. Comprobar el Core API: http://localhost:8000/api/health responde `{"status":"ok",...}`.
3. Usuarios de prueba: `docker exec inventaio-api python -m scripts.seed_usuarios`. Los crea si faltan y deja la clave en `admin123`; correrlo de nuevo no cambia nada más.
4. Frontend, en otra terminal de Ubuntu: `cd ~/InventaIO/frontend`, `npm ci` (la primera vez) y `npm run dev`. Requiere Node 22.12 o superior (`node -v`; con nvm, `nvm use`).
5. Abrir http://localhost:5173 en Chrome, en Windows: debe verse la pantalla de Login de InventAI/o.

Usuarios de prueba, todos con la clave `admin123`:

| Usuario | Nombre | Rol | Ubicación |
| --- | --- | --- | --- |
| `gerente@inventaio.co` | Carlos Martínez | gerente | Todas |
| `admin.principal@inventaio.co` | Laura Gómez | admin_sucursal | PRINCIPAL |
| `bodega@inventaio.co` | Diego Sánchez | admin_bodega | Todas |

## 2. Reglas para quien ejecuta

1. Ejecutar los bloques en orden (A a H). Dentro de un bloque, los casos en orden: algunos parten del estado del anterior.
2. Usar solo la app en http://localhost:5173. No editar archivos del proyecto, no ejecutar comandos y no tocar la base de datos.
3. Los números se comparan tal como se ven: separador de miles con punto y decimales con coma (`4.024`, `5,3 d`, `77,1`). Las cifras de dinero y los porcentajes usan punto decimal (`$737.9M`, `54.3%`, `15.4%`). Los textos se comparan sin importar mayúsculas: el rol del usuario se ve con mayúscula inicial ("Gerente") aunque en la página esté escrito en minúscula.
4. Marcar cada caso como:
   - **OK**: todo lo esperado se ve.
   - **FALLA**: algo no coincide. Anotar qué se esperaba, qué se vio y, si se puede, tomar una captura.
   - **BLOQUEADO**: no se pudo ejecutar, por ejemplo porque la página no carga. Anotar por qué.
5. Ante una FALLA, seguir con el caso siguiente. La excepción es el login: si un login con `admin123` no llega al Dashboard, detenerse, marcar como BLOQUEADO los casos que faltan y escribir el reporte. A-01 rechaza el login a propósito: que lo rechace es lo esperado.
6. Solo el bloque G cambia datos: la contraseña de `admin.principal`. Su último caso (G-05) la devuelve a `admin123` y **es obligatorio**. Si no se puede, avisar de inmediato: las pruebas automáticas dependen de esa clave (una persona puede restablecerla con el seed del paso 3 de la preparación).
7. Al terminar, completar la plantilla de la sección 11.
8. Usar Chrome maximizado. Por debajo de 1024 px de ancho (por ejemplo, con un panel lateral abierto o con la escala de Windows al 125–150 %) el menú lateral se oculta: se abre con el botón "Abrir menú" (tres rayas) de la esquina superior izquierda, y eso no es FALLA. Los avisos del propio Chrome (guardar contraseña, contraseña filtrada, traducir) no son de la app: cerrarlos sin guardar ni cambiar nada y anotarlos como observación.

## 3. Bloque A · Acceso y menú

**A-01 · Login con clave incorrecta**
- Pasos: en http://localhost:5173/login, escribir `gerente@inventaio.co` en "Correo electrónico" y `incorrecta` en "Contraseña"; clic en "Iniciar sesión".
- Esperado: aparece el mensaje "Credenciales inválidas" y se sigue en la pantalla de Login.

**A-02 · Login del gerente**
- Pasos: el correo `gerente@inventaio.co` sigue escrito y "Contraseña" todavía tiene `incorrecta`: borrar todo ese campo, escribir `admin123` e "Iniciar sesión".
- Esperado:
  - Se abre el Dashboard (la dirección termina en `/dashboard`).
  - El menú lateral muestra, en este orden: Dashboard, Inventario, Alertas, Reportes, Predicciones.
  - Abajo aparecen "Carlos Martínez", el rol "Gerente" y los botones "Cambiar contraseña" y "Cerrar sesión".
  - La barra superior (la franja blanca de arriba, por encima del título "Dashboard") no muestra ninguna sucursal. El selector "Todas las sucursales" a la derecha del título es parte de la página, no de la barra.

**A-03 · Ruta inexistente**
- Pasos: con la sesión del gerente, ir a http://localhost:5173/no-existe.
- Esperado: vuelve al Dashboard (`/dashboard`).

**A-04 · Cerrar sesión y entrar por URL sin sesión**
- Pasos: clic en "Cerrar sesión"; luego ir a http://localhost:5173/inventario.
- Esperado: después de cerrar sesión se ve el Login; al pedir `/inventario` sin sesión, vuelve al Login.

**A-05 · Login de admin.principal**
- Pasos: entrar con `admin.principal@inventaio.co` / `admin123`.
- Esperado:
  - Se abre el Dashboard.
  - La barra superior muestra la etiqueta "PRINCIPAL".
  - El menú tiene Dashboard, Inventario, Alertas, Reportes y Predicciones.
  - Abajo aparecen "Laura Gómez" y el rol "Admin Sucursal".

**A-06 · Login del admin_bodega (antes no tenía Dashboard)**
- Pasos: cerrar sesión y entrar con `bodega@inventaio.co` / `admin123`.
- Esperado:
  - Se abre el **Dashboard**, con el selector de sucursal.
  - El menú tiene Dashboard, Inventario, Alertas, Reportes y Predicciones.
  - Abajo aparecen "Diego Sánchez" y el rol "Admin Bodega".

## 4. Bloque B · Dashboard

Entrar como `gerente@inventaio.co`. El selector está arriba a la derecha.

**B-01 · Tarjetas con la fecha de la foto**
- Pasos: con "Todas las sucursales".
- Esperado: cuatro tarjetas.

  | Tarjeta | Subtítulo | Valor | Variación |
  | --- | --- | --- | --- |
  | Ventas del día | 31 dic 2025 | $56.8M | 1.4%, en rojo con flecha hacia abajo |
  | Ventas del mes | dic 2025 | $737.9M | 54.3%, en verde con flecha hacia arriba |
  | En riesgo | — | 1.500 | — |
  | Stock valorizado | — | $958.8M | — |

  No aparece ningún texto "Ventas hoy". Al pie se lee "Datos al 31 dic 2025".

**B-02 · Semáforo y alertas con sus nombres**
- Pasos: con "Todas las sucursales".
- Esperado:
  - **Semáforo de inventario:** una barra de cuatro tramos (verde, ámbar, rojo y violeta) y debajo "9.381 OK", "386 Bajo", "1.114 Crítico" y "220 Inconsistencia". Crítico e Inconsistencia son iguales a Stock crítico e Inconsistencia de inventario en la lista por tipo, y la tarjeta "En riesgo" (1.500) es la suma de Bajo y Crítico.
  - **Alertas activas:** Críticas 1.334, Altas 386 y Medias 2.732.
  - **Lista por tipo:** Inconsistencia de inventario 220, Stock crítico 1.114, Stock bajo 386, Sin movimiento 2.453 y Rotación baja 279. Los nombres van con tilde y sin guiones bajos.

**B-03 · Gráficas de ventas**
- Pasos: con "Todas las sucursales".
- Esperado:
  - Se ve la gráfica "Tendencia de ventas (30 días)", con la línea de ventas y la de MA 7d.
  - "Top 5 productos" muestra, de mayor a menor: VINO SANSON, GALL CARAVANA PLEGADIZA, VINO CARIÑOSO SURT, ARROZ ZULIA y HUEVOS. Los nombres largos se recortan con "...".

**B-04 · Opciones del selector**
- Pasos: abrir el selector.
- Esperado: Todas las sucursales, PRINCIPAL, LA 21, GLORIETA, Bodega Central. No aparecen SIN_SUCURSAL ni "BODEGA_CENTRAL".

**B-05 · Cada sucursal**
- Pasos: elegir cada sucursal en el selector y comparar.
- Esperado:

  | Sucursal | Ventas del día | Ventas del mes | En riesgo | Stock valorizado | Semáforo (OK / Bajo / Crítico / Inconsistencia) | Alertas (Críticas / Altas / Medias) |
  | --- | --- | --- | --- | --- | --- | --- |
  | PRINCIPAL | $36.7M, 2.2% verde | $471.8M, 65% verde | 340 | $350.6M | 3.611 / 138 / 202 / 95 | 297 / 138 / 873 |
  | LA 21 | $6.2M, 14.2% rojo | $88.2M, 39.9% verde | 207 | $79.1M | 1.641 / 60 / 147 / 40 | 187 / 60 / 767 |
  | GLORIETA | $13.8M, 3.9% rojo | $178.0M, 37.6% verde | 282 | $173.1M | 2.842 / 109 / 173 / 70 | 243 / 109 / 1.092 |

**B-06 · Vista de la Bodega Central**
- Pasos: elegir "Bodega Central".
- Esperado:
  - Solo dos tarjetas: En riesgo 671 y Stock valorizado $356.0M. No hay tarjetas de ventas.
  - Aparece la nota "La Bodega Central no vende: las ventas se ven por sucursal."
  - No se ven la tendencia ni el top de productos.
  - **Semáforo:** 1.287 OK, 79 Bajo, 592 Crítico y 15 Inconsistencia.
  - **Alertas:** Críticas 607, Altas 79 y Medias 0. Por tipo: Inconsistencia de inventario 15, Stock crítico 592, Stock bajo 79, Sin movimiento 0 y Rotación baja 0.

**B-07 · Volver a todas**
- Pasos: elegir "Todas las sucursales".
- Esperado: vuelven las cuatro tarjetas y las gráficas, con los valores de B-01.

**B-08 · admin.principal**
- Pasos: entrar como `admin.principal@inventaio.co`.
- Esperado: no hay selector, y los valores son los de PRINCIPAL en B-05.

**B-09 · admin_bodega**
- Pasos: entrar como `bodega@inventaio.co`.
- Esperado: hay selector, y con "Todas las sucursales" los valores son los de B-01 y B-02.

## 5. Bloque C · Inventario

Entrar como `gerente@inventaio.co` e ir a "Inventario". Cada caso parte de los filtros en su valor inicial: Todas las sucursales, Todos los estados, Todas las categorías y la búsqueda vacía. Para limpiar la búsqueda, borrar el texto y presionar Enter.

**C-01 · Vista inicial**
- Esperado:
  - Encabezado "11.101 productos · 31 dic 2025".
  - Columnas: Producto, Categoría, Sucursal, Stock, Stock Bodega, Reorden, Cobertura, Estado.
  - La tabla va ordenada por cobertura, de menor a mayor, así que empieza por el stock negativo. Primera fila: CEPILLO LAVA-AUTOS SUAVE FULLER de GLORIETA, Stock -44, con "◆ Inconsistencia".
  - Cada estado se ve en una sola línea, también "◆ Inconsistencia".
  - Al pie, "Página 1 de 741 · 11.101 total".

**C-02 · Categorías reales**
- Pasos: abrir el filtro de categorías.
- Esperado:
  - "Todas las categorías" y 33 categorías en orden alfabético, empezando por Aceites y sustitutos, Anchetas, Arroz y Aseo hogar.
  - Está "Licores".
  - No están "Abarrotes" ni "Delicatessen".

**C-03 · Filtro de categoría**
- Pasos: elegir "Licores".
- Esperado: "460 productos", todas las filas con categoría Licores y "Página 1 de 31".

**C-04 · Filtro de estado**
- Pasos: volver a "Todas las categorías" y elegir el estado "✕ Crítico"; luego elegir "◆ Inconsistencia".
- Esperado:
  - Las opciones del filtro son Todos los estados, ✓ OK, ⚠ Bajo, ✕ Crítico y ◆ Inconsistencia.
  - Con "✕ Crítico": "1.114 productos" y "Página 1 de 75"; ninguna fila tiene stock negativo.
  - Con "◆ Inconsistencia": "220 productos" y "Página 1 de 15"; todas las filas tienen stock negativo y cobertura "—".

**C-05 · Búsqueda, stock de la Bodega y distintivo**
- Pasos: escribir `ARROZ ZULIA` en "Buscar producto..." y presionar Enter.
- Esperado:
  - **Encabezado:** "25 productos".
  - **Primera fila:** ARROZ ZULIA \*500 GR · Arroz · PRINCIPAL · Stock 556 · Stock Bodega 4.024 · Reorden 732 · Cobertura 5,3 d · ⚠ Bajo.
  - **Fila de BODEGA_CENTRAL** (en esta misma página): ARROZ ZULIA \*500 GR, con la marca "Bodega" junto a la sucursal, Stock 4.024, Stock Bodega "—" y Cobertura 24,8 d.

**C-06 · Stock negativo como inconsistencia**
- Pasos: buscar `CEPILLO LAVA-AUTOS SUAVE`.
- Esperado:
  - "4 productos".
  - La fila de GLORIETA muestra Stock -44, Stock Bodega 20, Cobertura "—" y el estado "◆ Inconsistencia", con color violeta y en una sola línea.

**C-07 · Producto sin ventas**
- Pasos: buscar `FRIJOL CARGAMANTO GRANOS`.
- Esperado: "3 productos".

  | Sucursal | Stock | Stock Bodega | Cobertura | Estado |
  | --- | --- | --- | --- | --- |
  | PRINCIPAL | 38 | 25 | Sin ventas | ✓ OK |
  | GLORIETA | 16 | 25 | Sin ventas | ✓ OK |
  | BODEGA_CENTRAL (con la marca "Bodega") | 25 | — | 69,4 d | ✓ OK |

**C-08 · Cobertura alta que sí es real**
- Pasos: buscar `CERVEZA ANDINA LIGHT`.
- Esperado:
  - "2 productos".
  - PRINCIPAL: Stock 282, Stock Bodega 0, Cobertura "1.972,5 d". **No** debe decir "Sin ventas".
  - GLORIETA: Stock 136, Cobertura "425,9 d".

**C-09 · Inventario de la Bodega**
- Pasos: limpiar la búsqueda y elegir "Bodega Central" en el selector.
- Esperado: "1.973 productos"; todas las filas son de BODEGA_CENTRAL, con la marca "Bodega" y Stock Bodega "—".

**C-10 · Paginación**
- Pasos: volver a "Todas las sucursales"; clic en la flecha de página siguiente; luego en la anterior; avanzar otra vez a la página 2 y, desde ahí, elegir el estado "⚠ Bajo".
- Esperado: "Página 2 de 741", luego "Página 1 de 741"; con el filtro elegido desde la página 2, la paginación vuelve a la primera: "Página 1 de 26".

**C-11 · admin.principal ve su sucursal y el stock de la Bodega**
- Pasos: entrar como `admin.principal@inventaio.co`, ir a Inventario y buscar `HUEVOS *UND`.
- Esperado:
  - No hay selector de sucursal.
  - Sin búsqueda, el encabezado dice "4.046 productos" y todas las filas son de PRINCIPAL.
  - Con la búsqueda, el encabezado dice "1 producto" (en singular) y hay una sola fila: PRINCIPAL · Stock 489 · Stock Bodega 0 · Cobertura 2,9 d · ✕ Crítico.
  - Sin búsqueda y con el estado "◆ Inconsistencia": "95 productos", "Página 1 de 7", todas de PRINCIPAL.

## 6. Bloque D · Detalle de inventario

Entrar como `gerente@inventaio.co`, ir a Inventario y buscar `ARROZ ZULIA`.

**D-01 · Detalle de una sucursal**
- Pasos: clic en el nombre de la primera fila (ARROZ ZULIA \*500 GR de PRINCIPAL).
- Esperado: se abre a la derecha el panel "Detalle de inventario".
  - **Encabezado:** "ARROZ ZULIA \*500 GR", "Arroz · PRINCIPAL", "Código P3937 · Se vende por unidad" y el estado "⚠ Bajo".
  - **Datos:**

    | Dato | Valor |
    | --- | --- |
    | Stock actual | 556 |
    | Stock en la Bodega | 4.024 |
    | Stock mínimo | 314 |
    | Stock máximo | 3.137 |
    | Punto de reorden | 732 |
    | Cobertura | 5,3 d |

    Las cantidades no llevan unidad: la indica la descripción.
  - **Proveedor:** Distribuidora Valle S.A.S.
  - **Fotos de inventario:** "31 dic 2025: 556" y la nota "Hay una sola foto de inventario: todavía no hay una serie para graficar."

**D-02 · Cerrar el panel**
- Pasos: cerrar con la X; abrirlo otra vez y cerrar con la tecla Escape; abrirlo otra vez y hacer clic en la zona oscura, fuera del panel.
- Esperado: las tres formas cierran el panel. Un clic dentro del panel no lo cierra.

**D-03 · Detalle de la Bodega**
- Pasos: clic en ARROZ ZULIA \*500 GR de BODEGA_CENTRAL.
- Esperado: "Arroz · BODEGA_CENTRAL" con la marca "Bodega"; "Código P3937 · Se vende por unidad"; Stock actual 4.024; Stock en la Bodega "—"; Cobertura 24,8 d; estado "✓ OK".

**D-04 · Detalle con stock negativo**
- Pasos: buscar `CEPILLO LAVA-AUTOS SUAVE` y abrir la fila de GLORIETA.
- Esperado:
  - "Código P4221 · Se vende por unidad" y el estado "◆ Inconsistencia".
  - **Datos:** Stock actual -44, Stock en la Bodega 20, Stock mínimo 1, Stock máximo 6, Punto de reorden 2 y Cobertura "—".
  - **Proveedor:** Aseo Total de Colombia S.A.

**D-05 · Detalle como admin.principal**
- Pasos: entrar como `admin.principal@inventaio.co`, buscar `HUEVOS *UND` y abrir la fila.
- Esperado:
  - "Código P1632 · Se vende por unidad" y el estado "✕ Crítico".
  - **Datos:** Stock actual 489, Stock en la Bodega 0, Stock mínimo 511, Stock máximo 5.112, Punto de reorden 1.193 y Cobertura 2,9 d.
  - **Proveedor:** Lácteos del Cauca Ltda.

**D-06 · Producto que se vende por kilo**
- Pasos: como `gerente@inventaio.co`, buscar `PAPA PASTUSA` y abrir la fila de PRINCIPAL.
- Esperado:
  - **En la tabla:** "3 productos", con un decimal en las cantidades porque se vende por kilo:

    | Sucursal | Stock | Stock Bodega | Reorden | Cobertura | Estado |
    | --- | --- | --- | --- | --- | --- |
    | LA 21 | 67,7 | 0,0 | 257,0 | 1,8 d | ✕ Crítico |
    | PRINCIPAL | 77,1 | 0,0 | 86,0 | 6,3 d | ⚠ Bajo |
    | GLORIETA | 102,5 | 0,0 | 104,0 | 6,9 d | ⚠ Bajo |

  - **En el panel:** "PAPA PASTUSA \*KL", "Frutas y verduras · PRINCIPAL", "Código P1814 · Se vende por kilo (kg)" y el estado "⚠ Bajo".
  - **Datos, con un decimal:** Stock actual 77,1, Stock en la Bodega 0,0, Stock mínimo 37,0, Stock máximo 369,0, Punto de reorden 86,0 y Cobertura 6,3 d.
  - **Proveedor:** Frutos del Pacífico S.A.S.
  - **Fotos de inventario:** "31 dic 2025: 77,1".

## 7. Bloque E · Alertas

Entrar como `gerente@inventaio.co` e ir a "Alertas".

**E-01 · Vista inicial y paginación**
- Esperado:
  - **Encabezado:** "4.452 alertas activas · 31 dic 2025".
  - **Tarjetas de resumen:** Total 4.452, Críticas 1.334, Altas 386 y Medias 2.732.
  - **Lista:** 50 alertas y, al final, "Página 1 de 90 · 4.452 alertas".
  - **Primera alerta:** AZUCAR MORENA MANUELITA \*1KG, "BODEGA_CENTRAL" con la marca "Bodega" y "· Inconsistencia de inventario", la urgencia "Crítica" y el texto "Stock negativo en la foto (-300 unidades): verificar el conteo".

**E-02 · Filtro por el tipo nuevo**
- Pasos: abrir el filtro de tipos y elegir "Inconsistencia de inventario".
- Esperado:
  - Las opciones del filtro son Todos los tipos, Inconsistencia de inventario, Stock crítico, Stock bajo, Sin movimiento y Rotación baja.
  - Con el filtro, "220 alertas activas" y "Página 1 de 5 · 220 alertas".
  - Todas las alertas dicen "Inconsistencia de inventario", con urgencia "Crítica".

**E-03 · Última página**
- Pasos: con el filtro de E-02, avanzar hasta la página 5.
- Esperado:
  - "Página 5 de 5 · 220 alertas", con 20 alertas, y la flecha de página siguiente desactivada.
  - Los productos que se venden por kilo muestran el stock en kg con decimales, por ejemplo "UVA VERDE CIDRA", GLORIETA: "Stock negativo en la foto (-0,04 kg): verificar el conteo". Ninguna alerta muestra una cantidad redondeada a "-0", y las que se venden por unidad dicen "1 unidad" o "N unidades".

**E-04 · Filtro por urgencia**
- Pasos: tipo "Todos los tipos" y urgencia "Crítica".
- Esperado: "1.334 alertas activas" y "Página 1 de 27 · 1.334 alertas"; solo alertas de Inconsistencia de inventario o de Stock crítico.

**E-05 · Alertas de la Bodega**
- Pasos: urgencia "Todas las urgencias" y, en el selector, "Bodega Central".
- Esperado:
  - **Encabezado y resumen:** "686 alertas activas"; Total 686, Críticas 607, Altas 79 y Medias 0.
  - **Lista:** todas las alertas llevan la marca "Bodega" y solo hay Inconsistencia de inventario, Stock crítico y Stock bajo.
  - **Con el tipo "Sin movimiento":** el aviso "Sin alertas".

**E-06 · Actualizar**
- Pasos: volver a "Todas las sucursales" y "Todos los tipos"; clic en "Actualizar".
- Esperado: la lista se recarga y vuelve a mostrar "4.452 alertas activas".

**E-07 · admin.principal**
- Pasos: entrar como `admin.principal@inventaio.co` e ir a Alertas.
- Esperado:
  - No hay selector.
  - "1.308 alertas activas"; Críticas 297, Altas 138 y Medias 873.
  - "Página 1 de 27 · 1.308 alertas".
  - Todas las alertas son de PRINCIPAL y ninguna lleva la marca "Bodega".

**E-08 · admin_bodega**
- Pasos: entrar como `bodega@inventaio.co` e ir a Alertas.
- Esperado: hay selector, y con "Todas las sucursales" se ven los mismos totales de E-01.

## 8. Bloque F · Reportes

Entrar como `gerente@inventaio.co` e ir a "Reportes". Las fechas de los campos
Desde y Hasta se ven en el formato del idioma del navegador (por ejemplo,
`01/12/2025` o `12/01/2025`); se comparan por el día que indican.

**F-01 · Vista inicial: el mes de la última venta**
- Esperado:
  - **Encabezado:** "Reportes de ventas" y debajo "1 dic 2025 – 31 dic 2025"; arriba a la derecha, el selector con "Todas las sucursales".
  - **Filtros:** botones Mes (marcado), Trimestre, Año y Todo; Desde el 1 y Hasta el 31 de diciembre de 2025; agrupación "Día"; "Todas las categorías".
  - **Tarjetas:** Valor vendido $737.9M, Margen $149.7M, Cantidad 148.896 y Transacciones 53.098.
  - **"Ventas por día":** 31 barras, del "1 dic" al "31 dic".
  - **"Comparativa con el período anterior":** Este período $737.9M; "31 oct 2025 – 30 nov 2025" con $491.7M; 50.1% en verde con flecha hacia arriba.
  - **"Distribución por categorías":** Licores 15.4%, Panadería 9.7%, Aseo hogar 8.4%, Chocolate 5.5%, Arroz 5.2%, Café y sustitutos 5.2%, Lácteos 5.1% y Frutas y verduras 4.6%; al pie, "Y 24 categorías más."
  - **"Tendencia por sucursal":** tres líneas, con la leyenda GLORIETA, LA 21 y PRINCIPAL.
  - **"Inventario valorizado":** "Foto del 31 dic 2025: $958.8M".

    | Ubicación | Valor |
    | --- | --- |
    | Bodega Central (con la marca "Bodega") | $356.0M |
    | PRINCIPAL | $350.6M |
    | GLORIETA | $173.1M |
    | LA 21 | $79.1M |

    Por categoría: Aseo hogar $169.4M, Licores $91.9M, Panadería $73.6M, Cuidado personal $72.1M, Chocolate $66.2M, Café y sustitutos $56.7M, Arroz $56.3M y Aceites y sustitutos $47.2M.

**F-02 · Atajos de período**
- Pasos: clic en Trimestre, luego en Año y luego en Todo.
- Esperado:

  | Atajo | Encabezado | Agrupación | Valor vendido | Comparativa |
  | --- | --- | --- | --- | --- |
  | Trimestre | 1 oct 2025 – 31 dic 2025 | Semana | $1691.6M | "1 jul 2025 – 30 sep 2025", $1390.1M, 21.7% en verde |
  | Año | 1 ene 2025 – 31 dic 2025 | Mes | $5892.7M | "2 ene 2024 – 31 dic 2024", $5517.0M, 6.8% en verde |
  | Todo | 2 ene 2022 – 31 dic 2025 | Mes | $19977.9M | El aviso "No aplica a toda la historia: no hay un período anterior." |

  - **Trimestre:** "Ventas por semana", con 14 barras de "Sem 40 2025" a "Sem 1 2026". Del 29 al 31 de diciembre de 2025 es la semana 1 de 2026 en el calendario ISO.
  - **Año:** "Ventas por mes", con 12 barras de "ene 2025" a "dic 2025". La tendencia tiene una cuarta línea, "Sin sucursal": son las ventas sin terminal asignada, que llegan hasta septiembre de 2025. La línea va de feb a jul 2025 y septiembre se ve como un punto suelto, porque agosto no tiene ventas sin terminal.
  - **Todo:** barras de "ene 2022" a "dic 2025". No hay barras de "nov 2022" ni "dic 2022": la bodega no tiene ventas esos meses. En "feb 2023" la barra y las tres líneas de la tendencia bajan casi a $0: ese mes la bodega solo tiene ventas del día 1. También aparece la línea "Sin sucursal", con tramos cortados en los meses sin ventas sin terminal. Las gráficas tardan uno o dos segundos en dibujarse completas.

**F-03 · Agrupación a mano**
- Pasos: clic en Mes; cambiar la agrupación a "Semana".
- Esperado: "Ventas por semana" con 5 barras ("Sem 49 2025" a "Sem 1 2026"); las tarjetas no cambian ($737.9M).

**F-04 · Rango libre y fechas al revés**
- Pasos: agrupación "Día"; cambiar Desde al 15 de diciembre de 2025. Luego cambiar Desde al 31 de diciembre y Hasta al 1 de diciembre.
- Esperado:
  - Con el 15 de diciembre: ningún atajo marcado; encabezado "15 dic 2025 – 31 dic 2025"; Valor vendido $455.7M; 17 barras; comparativa "28 nov 2025 – 14 dic 2025" con $326.0M y 39.8% en verde.
  - Con las fechas al revés: el mensaje "La fecha inicial es posterior a la final." y no se ven los bloques de ventas; el inventario valorizado sigue visible.

**F-05 · Filtro de categoría**
- Pasos: clic en Mes y elegir la categoría "Licores".
- Esperado:
  - **Tarjetas:** Valor vendido $113.3M, Margen $19.7M, Cantidad 7.969 y Transacciones 1.724.
  - **Comparativa:** $113.3M; "31 oct 2025 – 30 nov 2025" con $20.8M; 444% en verde.
  - **Distribución:** sigue mostrando todas las categorías, con Licores (15.4%) en negrita y azul.
  - **Inventario valorizado:** "Foto del 31 dic 2025 · Licores: $91.9M"; PRINCIPAL $36.3M, Bodega Central $27.8M, GLORIETA $20.0M y LA 21 $7.8M; sin la tabla de categorías.

**F-06 · Una sucursal**
- Pasos: "Todas las categorías" y, en el selector, "GLORIETA".
- Esperado:
  - **Tarjetas:** $178.0M, Margen $32.9M, Cantidad 40.217 y Transacciones 13.652.
  - **Comparativa:** "31 oct 2025 – 30 nov 2025" con $133.5M y 33.3% en verde.
  - **Distribución:** empieza por Licores 16.7%.
  - **Tendencia:** una sola línea, GLORIETA.
  - **Inventario valorizado:** $173.1M, solo GLORIETA; por categoría empieza por Aseo hogar $22.6M y Licores $20.0M.

**F-07 · La Bodega Central**
- Pasos: elegir "Bodega Central" en el selector.
- Esperado:
  - La nota "La Bodega Central no vende: las ventas se ven por sucursal. Aquí se ve su inventario valorizado."
  - No se ven tarjetas, comparativa, distribución ni tendencia.
  - **Inventario valorizado:** $356.0M, una fila "Bodega Central" con la marca "Bodega"; por categoría: Aseo hogar $77.6M, Arroz $36.5M, Panadería $35.1M, Chocolate $31.1M y Licores $27.8M, entre otras.

**F-08 · admin.principal**
- Pasos: entrar como `admin.principal@inventaio.co` e ir a Reportes.
- Esperado:
  - No hay selector de sucursal.
  - **Tarjetas:** $471.8M, Margen $98.7M, Cantidad 86.388 y Transacciones 30.933.
  - **Comparativa:** $293.5M en el período anterior y 60.7% en verde.
  - **Distribución:** empieza por Licores 15.1%.
  - **Tendencia:** una sola línea, PRINCIPAL.
  - **Inventario valorizado:** $350.6M, solo PRINCIPAL; por categoría empieza por Aseo hogar $57.3M, Cuidado personal $37.5M y Licores $36.3M.

**F-09 · admin_bodega**
- Pasos: entrar como `bodega@inventaio.co` e ir a Reportes.
- Esperado: hay selector y, con "Todas las sucursales", se ven los valores de F-01.

## 9. Bloque G · Cambio de contraseña

Entrar como `admin.principal@inventaio.co`. **G-05 es obligatorio**: deja la clave otra vez en `admin123`.

**G-01 · Validaciones del formulario**
- Pasos:
  1. Clic en "Cambiar contraseña".
  2. Llenar "Contraseña actual" con `admin123`, y "Nueva contraseña" y "Confirmar nueva contraseña" con `abc`; clic en "Guardar".
  3. Borrar los dos campos nuevos, escribir `Prueba2026` en "Nueva contraseña" y `Prueba2027` en "Confirmar nueva contraseña"; clic en "Guardar".
- Esperado:
  - Se abre el formulario "Cambiar contraseña".
  - Con `abc`: "La nueva contraseña debe tener al menos 8 caracteres".
  - Con claves distintas: "La confirmación no coincide con la nueva contraseña".

**G-02 · Contraseña actual incorrecta**
- Pasos: "Contraseña actual" `incorrecta`; nueva y confirmación `Prueba2026`; "Guardar".
- Esperado: "La contraseña actual es incorrecta".

**G-03 · Nueva igual a la actual**
- Pasos: actual, nueva y confirmación `admin123`; "Guardar".
- Esperado: "La nueva contraseña debe ser diferente a la actual".

**G-04 · Cambio exitoso**
- Pasos: actual `admin123`; nueva y confirmación `Prueba2026`; "Guardar". Cerrar el formulario con la X, cerrar sesión y entrar con `admin.principal@inventaio.co` / `admin123`. Luego entrar con `Prueba2026`.
- Esperado: "Contraseña actualizada exitosamente"; con `admin123` aparece "Credenciales inválidas"; con `Prueba2026` entra al Dashboard.

**G-05 · Restaurar la clave (obligatorio)**
- Pasos: con la sesión de G-04, "Cambiar contraseña": actual `Prueba2026`; nueva y confirmación `admin123`; "Guardar". Cerrar el formulario con la X (mientras está abierto tapa el menú), cerrar sesión y entrar con `admin123`.
- Esperado: "Contraseña actualizada exitosamente" y el login con `admin123` funciona.

## 10. Bloque H · Predicciones

Vista de INV-26. Entrar como `gerente@inventaio.co` e ir a "Predicciones". Las
cifras salen del pronóstico y de la foto al 2025-12-31. Para elegir un producto:
escribir el código en "Buscar producto por nombre o código" y hacer clic en el
resultado. La gráfica se juzga por su forma; sus cifras se leen en el texto de
debajo.

**H-01 · Vista inicial**
- Esperado:
  - Encabezado "Predicciones" y debajo "Demanda prevista a 15 días hábiles". No hay selector de horizonte.
  - Arriba a la derecha, el selector de sucursal dice "Elegir sucursal". Sus opciones son exactamente Elegir sucursal, PRINCIPAL, LA 21 y GLORIETA: ni "Todas las sucursales" ni "Bodega Central".
  - El buscador dice "Buscar producto por nombre o código" y debajo hay un aviso azul: "Busque un producto por nombre o código y elija una sucursal para ver su pronóstico."

**H-02 · Búsqueda por código y por nombre**
- Pasos:
  1. Escribir `P1632` en el buscador.
  2. Borrar y escribir `ARROZ`.
  3. Borrar y escribir `xyz`.
  4. Pulsar la tecla Esc.
- Esperado:
  - Con `P1632`, un solo resultado: "HUEVOS *UND · P1632 · Huevos".
  - Con `ARROZ`, 20 resultados y al pie "Se muestran 20 de 71 productos: escriba más para acotar."
  - Con `xyz`, "Ningún producto coincide con «xyz»."
  - Esc borra el texto y cierra la lista.

**H-03 · HUEVOS en PRINCIPAL: riesgo urgente**
- Pasos: buscar `P1632`, clic en "HUEVOS *UND" y elegir PRINCIPAL en el selector.
- Esperado:
  - Debajo del buscador, "HUEVOS *UND" y "Código P1632 · Huevos · Se vende por unidad · PRINCIPAL". El aviso azul desaparece.
  - **"Pronóstico a 15 días hábiles":**
    - Demanda prevista "3.366 unidades", con "Mediana (q50) en 15 días hábiles".
    - Límite de negocio "4.609 unidades", con "Cuantil de negocio (α = 0,893)".
    - Riesgo según el pronóstico "2,2 días hábiles", con la insignia roja "Urgente".
  - **"Interpretación":** "Demanda intermitente. Proyección: 3.366 unidades en 15 días hábiles. Cobertura recomendada: hasta 4.609 unidades." y "Rama del modelo: Demanda intermitente".
  - **"Inventario · foto del 31 dic 2025":** Stock actual "489 unidades" ("Foto del 31 dic 2025") y Cobertura del inventario "2,9 d" con "✕ Crítico".
  - **La gráfica "Ventas en ventanas de 15 días hábiles y pronóstico":**
    - 8 barras azules sólidas rotuladas 16 sep, 2 oct, 17 oct, 1 nov, 16 nov, 1 dic, 16 dic y 31 dic.
    - Al final, una barra clara de borde punteado rotulada "Pronóstico IA".
    - Una línea naranja punteada (el cuantil) casi a la altura de la barra "31 dic" y una línea verde (el stock) cerca de la base.
    - Sin bandas ni zonas sombreadas.
    - El subtítulo dice "Ventas sin devoluciones. La última ventana termina el 31 dic 2025 y el pronóstico la sigue." y la leyenda, "Ventas" y "Pronóstico IA (q50)".
  - Debajo de la gráfica, "Cuantil de negocio (α = 0,893): 4.609 unidades" y "Stock actual: 489 unidades". Al pie de la página, "Features al 31 dic 2025 · Modelo entrenado el 25 sep 2026".
  - Al pasar el mouse por la barra "31 dic" se ve "17 dic 2025 – 31 dic 2025" y "Ventas : 4.608 unidades". Por la barra "Pronóstico IA", "Próximos 15 días hábiles" y "Pronóstico IA (q50) : 3.366 unidades".

**H-04 · ARROZ ZULIA en PRINCIPAL: las dos lecturas de riesgo no coinciden**
- Pasos: con PRINCIPAL elegida, buscar `P3937` y clic en "ARROZ ZULIA *500 GR".
- Esperado:
  - Demanda prevista "1.251 unidades" y límite "1.660 unidades" (α = 0,893).
  - Riesgo según el pronóstico "6,7 días hábiles" con la insignia "Alta".
  - Stock actual "556 unidades" y cobertura del inventario "5,3 d" con "⚠ Bajo".
  - "Rama del modelo: Demanda estable".
  - Que el pronóstico diga "Alta" y el semáforo "Bajo" es lo esperado: son dos lecturas distintas, cada una con su rótulo.

**H-05 · HUEVOS en GLORIETA: perecedero**
- Pasos: buscar `P1632`, clic en "HUEVOS *UND" y elegir GLORIETA.
- Esperado:
  - Demanda prevista "3.871 unidades".
  - Límite de negocio "3.094 unidades", **menor** que la demanda prevista, con "Cuantil de negocio (α = 0,167)" y la nota "Cuantil bajo: queda bajo la mediana para evitar merma en un perecedero. No es una cota de reposición."
  - Riesgo "1,3 días hábiles" con "Urgente"; stock "341 unidades"; cobertura "1,3 d" con "✕ Crítico".
  - "Rama del modelo: Demanda estable, producto perecedero".
  - En la gráfica, la línea naranja queda por debajo del tope de la barra "Pronóstico IA". Debajo: "Cuantil de negocio (α = 0,167): 3.094 unidades, bajo la mediana: no es una cota de reposición".

**H-06 · PAPA PASTUSA en PRINCIPAL: se vende por kilo**
- Pasos: elegir PRINCIPAL, buscar `P1814` y clic en "PAPA PASTUSA *KL".
- Esperado:
  - "Código P1814 · Frutas y verduras · Se vende por kilo (kg) · PRINCIPAL".
  - Demanda prevista "135,7 kg" y límite "199,7 kg".
  - Riesgo "8,5 días hábiles" con "Alta".
  - Stock actual "77,1 kg" y cobertura "6,3 d" con "⚠ Bajo".
  - Debajo de la gráfica, "Stock actual: 77,1 kg".

**H-07 · FRIJOL CARGAMANTO en PRINCIPAL: historia insuficiente**
- Pasos: con PRINCIPAL elegida, buscar `02458` y clic en "FRIJOL CARGAMANTO GRANOS DEL ORIENTE * 460 GR".
- Esperado:
  - En "Pronóstico a 15 días hábiles", un mensaje rojo con el botón "Reintentar": "No hay historia suficiente para producto_id=02458, sucursal_id=PRINCIPAL: 0 días con venta hasta 2025-12-31 (el modelo exige al menos 30)". No hay tarjetas de pronóstico.
  - El inventario sí se ve: Stock actual "38 unidades" y cobertura "Sin ventas" con "✓ OK".
  - En la gráfica, el aviso "El producto no vendió en PRINCIPAL entre el 2 sep 2025 y el 31 dic 2025."; las 8 ventanas sin barra visible (valen 0) y ninguna barra "Pronóstico IA". El subtítulo termina en "…termina el 31 dic 2025." y la leyenda solo dice "Ventas".
  - Debajo de la gráfica, solo "Stock actual: 38 unidades". No aparece la línea "Features al…".

**H-08 · admin.principal: su sucursal, sin selector**
- Pasos: cerrar sesión, entrar con `admin.principal@inventaio.co` / `admin123` e ir a "Predicciones". Buscar `P1632` y clic en "HUEVOS *UND".
- Esperado:
  - No hay selector de sucursal. Antes de elegir el producto, el aviso dice "Busque un producto por nombre o código para ver su pronóstico."
  - Al elegirlo: "Código P1632 · Huevos · Se vende por unidad · PRINCIPAL" y las mismas cifras de H-03 (3.366 unidades, 2,2 días hábiles "Urgente", 489 unidades).

**H-09 · admin_bodega: elige sucursal física**
- Pasos: cerrar sesión, entrar con `bodega@inventaio.co` / `admin123` e ir a "Predicciones". Buscar `P1632`, clic en "HUEVOS *UND" y elegir LA 21.
- Esperado:
  - Las opciones del selector son Elegir sucursal, PRINCIPAL, LA 21 y GLORIETA (sin "Bodega Central").
  - Demanda prevista "1.567 unidades" y límite "1.253 unidades" (α = 0,167), con la nota del cuantil bajo.
  - Riesgo "5,0 días hábiles" con "Urgente". La cuenta da 5,03, y los días se comparan como se ven.
  - Stock actual "525 unidades" y cobertura "6,6 d" con "⚠ Bajo".

## 11. Reporte

Completar al terminar:

```markdown
# Resultado de las pruebas de pantallas · INV-26 fix

Fecha: AAAA-MM-DD · Ejecutó: (persona o Cowork) · Navegador: Chrome

| Caso | Resultado | Observación |
| --- | --- | --- |
| A-01 | OK | |
| ... | | |

Resumen: N casos OK, N con FALLA, N bloqueados.
Contraseña de admin.principal restaurada a admin123 (G-05): sí / no.

## Fallas
Por cada FALLA: caso, qué se esperaba, qué se vio y captura si la hay.
```

## 12. Cómo pedírselo a Cowork

Con la preparación de la sección 1 hecha y la app abierta en Chrome, en una
tarea de Cowork con acceso a la carpeta del repositorio (desde Windows,
`\\wsl.localhost\Ubuntu\home\alejo\InventaIO`):

> Lee `docs/INV-26-pruebas-pantallas.md` y ejecuta los bloques A a H en Chrome, sobre
> http://localhost:5173, siguiendo las reglas de la sección 2. No edites archivos del
> proyecto ni ejecutes comandos. Al terminar, escribe el reporte con la plantilla de la
> sección 11 en `resultados-INV-26-pantallas.md`, en la raíz de la carpeta, y avísame si
> algún caso falló. El caso G-05 es obligatorio: deja la clave de admin.principal en admin123.

Conviene empezar con un piloto: pedirle solo el bloque A y revisar el reporte
antes de lanzar el resto.
