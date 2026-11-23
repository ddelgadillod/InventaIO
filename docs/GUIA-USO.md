# Guía de uso de InventAI/o para Vera

Fragmentos cortos de la guía del cliente para que Vera responda «¿cómo hago…?» y «¿por qué sale esta cifra?» (INV-40, criterio 5). La fuente es la guía del cliente en PDF:
- **Parte II**, «Guía del sistema», versión 1.1 del 8 de octubre de 2026;
- **Parte III**, «Guía de Vera», versión 1.0 del 28 de octubre de 2026.

Se tomaron solo los capítulos de uso y de cómo salen las cifras, revisados contra la aplicación del 18 de noviembre de 2026.

**Reglas del corpus (criterio 6).**
- Sin cifras del negocio: las cifras siempre salen de las herramientas.
- Los únicos números son reglas del sistema. Una prueba los compara con el código (`nlp_agent/tests/test_guia.py`).
- Sin nombres de sucursales, de productos ni de personas.
- La fecha de la foto de inventario no se escribe: la dice cada pantalla.

**Formato.** Cada sección `##` es un fragmento con cuatro campos:
- **Sección:** la de la guía en PDF, que Vera cita.
- **Fecha:** la de la guía o la de la revisión contra la aplicación.
- el texto;
- **También se dice:** las palabras con que la gente pregunta.

**Construcción.** `python -m conocimiento.construir`, desde `nlp_agent/`, la junta con el glosario en `nlp_agent/conocimiento/corpus.json`.

# Parte II · Guía del sistema

## Quién puede ver qué

**Sección.** Parte II · 10.2 Quién puede ver qué

**Fecha.** 2026-10-08

Cada persona entra con su correo y su contraseña y tiene un rol:
- **El gerente:** ve todas las sucursales y la Bodega Central.
- **El administrador de bodega:** también ve todas las ubicaciones.
- **El administrador de sucursal:** solo ve la suya.

El permiso no depende de la pantalla: lo revisa el Core API en cada consulta. Por eso, si alguien pide datos de una ubicación que no le corresponde, la respuesta es «sin permiso», tanto en las pantallas como en Vera. Los usuarios los crea el equipo técnico: todavía no hay una pantalla para administrarlos.

**También se dice.** Permisos, roles, qué puedo ver, ver otra sucursal, acceso a las sucursales, por qué no veo las demás sucursales, usuarios, crear un usuario.

## La sesión y los intentos fallidos

**Sección.** Parte II · 10.2 Quién puede ver qué

**Fecha.** 2026-11-18

**La sesión.** Al entrar, la aplicación recibe una llave temporal que se renueva sola mientras se usa. Si ya no se puede renovar, vuelve a la pantalla de acceso con el aviso «Sesión expirada»: basta con entrar de nuevo.

**La contraseña.** Se guarda cifrada: nadie puede leerla, solo comprobarla.

**Los intentos fallidos.** Después de varios intentos fallidos seguidos, el acceso se bloquea por unos minutos con el aviso «Demasiados intentos fallidos. Intenta de nuevo en…». Hay que esperar ese tiempo, aunque la clave sea la correcta.

**También se dice.** Se me cerró la sesión, sesión vencida, me sacó de la aplicación, no me deja entrar, bloqueado, demasiados intentos, olvidé la contraseña.

## La foto de inventario: de qué fecha son los datos

**Sección.** Parte II · 10.3 La foto de inventario y el calendario del negocio

**Fecha.** 2026-10-08

El inventario es una foto del conteo físico en una fecha de corte, y todas las cifras se calculan a esa fecha. Todas las pantallas la muestran («Datos al …», «Foto del …»). Por eso, en la aplicación, «hoy» es la fecha de la foto, y «Ventas del día» son las de ese día. La foto no se actualiza sola: cambia cuando se carga un inventario nuevo.

Si llega una foto más nueva que las últimas ventas cargadas, el sistema no calcula recomendaciones y lo avisa, para no mezclar fechas.

**También se dice.** Fecha de los datos, por qué dice esa fecha, datos desactualizados, de cuándo son los datos, hoy, fecha de corte, último inventario, por qué no es la fecha de hoy.

## Día hábil

**Sección.** Parte II · 10.3 La foto de inventario y el calendario del negocio

**Fecha.** 2026-10-08

Un día hábil es un día de operación del negocio:
- en la historia, los días con al menos una venta;
- hacia adelante, todos los días del calendario salvo los cierres programados que se conocen: el primero de enero y el Viernes Santo.

Los domingos y los festivos con venta cuentan. Por eso un pedido puede llegar un domingo, y los 15 días hábiles del pronóstico son unas dos semanas y media de calendario.

**También se dice.** Días hábiles, qué cuenta como día hábil, domingos, festivos, días laborales, por qué llega un domingo, calendario del negocio.

## Fecha del modelo de pronóstico

**Sección.** Parte II · 10.3 La foto de inventario y el calendario del negocio

**Fecha.** 2026-10-08

Las pantallas de pronóstico dicen cuándo se entrenó el modelo («Modelo entrenado el …») y hasta cuándo llegan los datos que usó («Features al …»). La fecha del modelo se escribe en hora universal (UTC). Si el modelo se exportó en la noche en Colombia, la pantalla puede mostrar el día siguiente.

**También se dice.** Modelo entrenado, fecha del modelo, cuándo se entrenó, features al, hora universal, por qué sale otro día.

## El pronóstico de un producto

**Sección.** Parte II · 11.1 El pronóstico de un producto en una sucursal

**Fecha.** 2026-10-08

El pronóstico es siempre a 15 días hábiles: no hay selector de horizonte, porque el modelo solo se entrenó para ese plazo. Para un producto en una sucursal entrega:
- **la demanda prevista:** la cifra central, o mediana;
- **el límite de negocio:** con su nivel de servicio;
- **el riesgo según el pronóstico:** en días hábiles;
- **una interpretación;**
- **la rama del modelo que lo calculó.**

Los productos de demanda estable usan el promedio móvil de las ventas recientes. Los de demanda intermitente usan un modelo LightGBM que aprende cuántas veces su nivel habitual se venderá.

**También se dice.** Pronóstico, predicción, cuánto se va a vender, demanda prevista, horizonte, a cuántos días, cómo se calcula el pronóstico, cálculo de la predicción.

## Por qué un producto no tiene pronóstico

**Sección.** Parte II · 11.1 El pronóstico de un producto en una sucursal

**Fecha.** 2026-10-08

Hay dos casos en que no hay pronóstico:
- **Le falta historia.** Un producto necesita al menos 30 días con venta en esa sucursal. Si no los tiene, Predicciones lo dice con el motivo («No hay historia suficiente…») y el botón «Reintentar». Es una respuesta correcta, no una falla.
- **Es la Bodega Central.** No tiene pronóstico porque no vende al público: solo despacha. Lo que necesita sale de lo que necesitan las sucursales.

Sin pronóstico, el producto tampoco entra en las compras ni en los traslados sugeridos.

**También se dice.** Sin pronóstico, no hay historia suficiente, no tiene predicción, la bodega no tiene pronóstico, por qué no sale el pronóstico, producto nuevo, historia mínima.

## Límite de negocio y productos perecederos

**Sección.** Parte II · 11.1 El pronóstico de un producto en una sucursal

**Fecha.** 2026-10-08

El límite de negocio es una cifra del pronóstico pensada para decidir cuánto tener.

En los productos que se dañan, como huevos, lácteos o frutas, pasarse cuesta más que quedarse corto, porque lo que sobra se vuelve merma. Por eso su límite queda por debajo de la demanda prevista. La pantalla lo avisa en naranja: «Cuantil bajo: queda bajo la mediana para evitar merma en un perecedero. No es una cota de reposición».

En los demás productos, el límite queda por encima de la demanda prevista.

**También se dice.** Límite de negocio, cuantil, alfa, por qué el límite es menor, perecederos, merma, nivel de servicio, cota de reposición.

## Demanda intermitente, estable y perecedera

**Sección.** Parte II · 11.1 El pronóstico de un producto en una sucursal

**Fecha.** 2026-10-08

El modelo separa los productos en tres ramas según cómo se venden:
- **Demanda intermitente:** muchos días sin venta. Es la mayoría de los productos. Sus pronósticos pueden ser pequeños o cero.
- **Demanda estable, no perecedera.**
- **Demanda estable, perecedera.**

Predicciones muestra la rama y su interpretación junto a cada pronóstico.

**También se dice.** Rama del modelo, intermitente, estable, por qué casi todos son intermitentes, tipo de demanda, pronóstico cero, días sin venta.

## Cobertura y riesgo: dos formas de medir

**Sección.** Parte II · 11.2 Dos formas de medir el riesgo de quedarse sin producto

**Fecha.** 2026-10-08

El sistema mide el riesgo de quedarse sin producto de dos maneras:

| | Cobertura (el semáforo) | Riesgo según el pronóstico |
| --- | --- | --- |
| Qué es | Cuántos días alcanza el stock | Cuántos días hábiles alcanza el stock si se vende lo pronosticado |
| Cálculo | Stock ÷ venta diaria promedio de siempre | Stock ÷ (demanda prevista ÷ 15) |
| Unidad | Días corridos («d») | Días hábiles |
| Cortes | Crítico con menos de 3 días, Bajo de 3 a menos de 7, OK con 7 o más | Urgente con 5 o menos, Alta con más de 5 y hasta 10, Normal con más de 10 |
| Dónde aparece | Dashboard, Inventario y Alertas | Predicciones y Recomendaciones |

No se contradicen: responden preguntas distintas. Por eso un mismo producto puede verse «Bajo» en Inventario y con urgencia «Alta» en Predicciones.

**También se dice.** Cobertura, días de cobertura, para cuántos días alcanza, cuánto me dura el stock, semáforo, riesgo, días hábiles que alcanza, por qué sale bajo en una pantalla y alta en otra, etiquetas distintas.

## Distinta urgencia para el mismo producto en dos pantallas

**Sección.** Parte II · 11.2 Dos formas de medir el riesgo de quedarse sin producto

**Fecha.** 2026-10-08

Un producto en el borde de un corte puede verse con urgencias distintas en Predicciones y en Recomendaciones (o en las alertas con IA):
- **Predicciones** redondea los días a un decimal antes de comparar.
- **Recomendaciones** compara el valor exacto y además cuenta lo que ya viene en camino por traslado.

Las dos reglas están documentadas. Unificarlas es una decisión pendiente del negocio.

**También se dice.** Urgencia distinta, dos etiquetas, no coincide la urgencia, redondeo, por qué en una pantalla es urgente y en otra alta.

## El indicador «En riesgo» y las inconsistencias

**Sección.** Parte II · 11.2 Dos formas de medir el riesgo de quedarse sin producto

**Fecha.** 2026-10-08

**«En riesgo».** El indicador del Dashboard suma los productos en estado Bajo y Crítico del semáforo.

**Las inconsistencias.** Tienen tramo y alerta propios, y no tienen cobertura («—»). Un stock negativo no es falta de producto: es un descuadre que hay que revisar.

**Los símbolos del estado.** El estado se escribe con texto y símbolo, no solo con color:
- ✓ OK;
- ⚠ Bajo;
- ✕ Crítico;
- ◆ Inconsistencia (el rombo).

**También se dice.** En riesgo, productos en riesgo, qué cuenta en riesgo, rombo, símbolo, inconsistencia, stock negativo, colores del semáforo, qué significa el color.

## Traslados primero, compras después

**Sección.** Parte II · 11.3 Traslados primero, compras después

**Fecha.** 2026-10-08

Antes de comprar, el sistema revisa si lo que le falta a una sucursal le sobra a otra ubicación.

**Lo que falta.** Cada ubicación debería tener, al menos, la demanda prevista de los próximos 15 días hábiles. Lo que le falta es su déficit.

**Lo que sobra.** El excedente es lo que pasa del límite de negocio más un margen. El origen conserva unas unidades de exhibición. En la Bodega Central todo el stock positivo es excedente, porque no vende.

**El reparto.** La Bodega es siempre el primer origen. El excedente se reparte empezando por la ubicación con menos cobertura. Lo que no se alcanza a cubrir, el déficit neto, pasa a compras.

**También se dice.** Cómo decide trasladar o comprar, traslados, transferencias, excedente, déficit, de dónde sale el traslado, por qué se traslada antes de comprar, mover producto entre sucursales.

## Cuándo llega un traslado y «Llega tarde»

**Sección.** Parte II · 11.3 Traslados primero, compras después

**Fecha.** 2026-10-08

**Cuándo llega.** Si no hay días fijos de salida, un traslado llega 2 días hábiles después de la foto.

**«Llega tarde».** Se marca cuando el producto se agota antes de que llegue el traslado o el pedido. Se marca, pero no se bloquea: es una señal de que hay que actuar antes.

**Tamaño mínimo.** Un traslado no baja de una cantidad mínima. En los productos por kilo se descuenta una parte por pérdida.

**También se dice.** Llega tarde, llegada del traslado, cuándo llega, por qué sale llega tarde, cantidad mínima de un traslado, mínimo para trasladar.

## Perecederos y productos con frío

**Sección.** Parte II · 11.3 Traslados primero, compras después

**Fecha.** 2026-10-08

Los perecederos y los productos que necesitan frío no pasan por la Bodega Central: se compran directo a la sucursal, en el pedido semanal. Para ellos, pasarse cuesta más que quedarse corto. Por eso su pronóstico usa un límite más bajo y su margen de sobrante es más chico.

**También se dice.** Perecederos, frío, refrigerados, por qué no pasan por la bodega, compra directa a la sucursal, lácteos, frutas, carnes.

## Calendario de pedidos

**Sección.** Parte II · 11.4 Las compras recomendadas: calendario y cantidades

**Fecha.** 2026-10-08

El sistema no pide «cuando se acuerda»: sigue el calendario de pedidos del negocio.
- **Grupo semanal:** pedido cada martes. Son los productos que se dañan o necesitan frío, y van directo a la sucursal.
- **Grupo quincenal:** pedido los días 2 y 16 de cada mes. Es todo lo demás. Llega a la Bodega y de ahí pasa a la sucursal 2 días hábiles después.

El plazo del proveedor es de 5 días hábiles para todos. Es un supuesto, porque todavía no hay datos reales de compras.

Recomendaciones muestra el calendario arriba de la pestaña Compras: el pedido, la llegada, el pedido siguiente y hasta cuándo cubre.

**También se dice.** Qué días se pide, calendario de pedidos, cuándo se hacen los pedidos, días de pedido, pedido semanal, pedido quincenal, plazo del proveedor, tiempo de entrega, cuándo llega la compra.

## Cómo se calcula una compra

**Sección.** Parte II · 11.4 Las compras recomendadas: calendario y cantidades

**Fecha.** 2026-10-08

En cada fecha de pedido, el sistema compra lo necesario para que el stock alcance hasta que llegue el pedido siguiente. P es el número de días hábiles que hay que cubrir. Para cada producto y sucursal calcula tres cifras:
- **Posición:** el stock (si es negativo, cuenta como cero) más lo que ya viene por traslado.
- **Punto de pedido:** demanda prevista × P ÷ 15.
- **Nivel de reposición:** el mayor entre el límite de negocio y la demanda prevista, × P ÷ 15.

Si la posición está por debajo del punto de pedido, se compra la diferencia entre el nivel y la posición, redondeada hacia arriba.

**También se dice.** Cómo se calcula la compra, cantidad a comprar, cuánto pedir, punto de pedido, nivel de reposición, posición, fórmula de la compra, por qué recomienda esa cantidad.

## La Bodega como intermediaria en las compras

**Sección.** Parte II · 11.4 Las compras recomendadas: calendario y cantidades

**Fecha.** 2026-10-08

**Una sola compra para la Bodega.** Cuando un producto del grupo quincenal le hace falta a varias sucursales, se compra una sola línea para la Bodega Central: la suma de lo que necesitan, menos lo que la Bodega ya tiene.

**Productos que no se compran.** Si la Bodega ya tiene lo que sus sucursales necesitan, el producto no se compra. Aparece en «Cubrir con traslado desde la Bodega».

**Inconsistencias.** Una compra también puede nacer de una inconsistencia: el motivo dice «Stock negativo».

**También se dice.** Compra para la bodega, compras consolidadas, cubrir con traslado, por qué no se compra, motivo de la compra, stock negativo.

## Urgencia de una compra

**Sección.** Parte II · 11.4 Las compras recomendadas: calendario y cantidades

**Fecha.** 2026-10-08

La urgencia de una compra depende de los días hábiles que alcanza el stock:
- **Urgente:** se agota en 5 días hábiles o menos.
- **Alta:** se agota en más de 5 y hasta 10.
- **Normal:** alcanza para más de 10.

Las compras que llegan después de que el producto se agote se marcan «Llega tarde», pero no se bloquean.

**También se dice.** Urgencia, urgente, prioridad de compra, qué es urgente, alta, normal, días hasta agotarse.

## Los tipos de alerta por reglas

**Sección.** Parte II · 11.5 Las alertas

**Fecha.** 2026-10-08

Las alertas ordenan qué mirar primero. Las de reglas son de cinco tipos:
- **inconsistencia de inventario;**
- **stock crítico;**
- **stock bajo;**
- **sin movimiento;**
- **rotación baja.**

Cada una tiene una urgencia: crítica, alta o media. Las críticas van arriba.

La Bodega Central no tiene alertas de «sin movimiento» ni de «rotación baja», porque no vende.

**También se dice.** Tipos de alerta, qué alertas hay, alertas por reglas, sin movimiento, rotación baja, stock crítico, urgencia de la alerta, crítica, alta, media.

## Inconsistencia de inventario y «verificar el conteo»

**Sección.** Parte II · 11.5 Las alertas

**Fecha.** 2026-10-08

Una inconsistencia quiere decir que el inventario registra más salidas que entradas para ese producto, y el saldo queda negativo. No se corrigió a cero porque no hay evidencia de que sea un error de captura.

La alerta no dice «falta producto»: dice «verifique el conteo». En Recomendaciones, la acción es «Compra urgente» cuando hay pronóstico, y «Verificar conteo» cuando no lo hay, como en la Bodega.

**También se dice.** Verificar el conteo, stock negativo, inconsistencia, saldo negativo, descuadre, qué hago con una inconsistencia, conteo físico.

## Entrar a la aplicación

**Sección.** Parte II · 12.1 Entrar y moverse

**Fecha.** 2026-11-18

Se entra con el correo y la contraseña, y se pulsa «Iniciar sesión», que abre el Dashboard.

**Si algo falla:**
- con datos incorrectos aparece «Credenciales inválidas»;
- si el servidor no responde, el aviso lo dice («No hay conexión con el servidor» o un error del servidor);
- después de varios intentos fallidos, el acceso se bloquea por unos minutos.

**También se dice.** Iniciar sesión, entrar, login, no puedo entrar, credenciales inválidas, error al entrar, no hay conexión.

## Moverse por la aplicación

**Sección.** Parte II · 12.1 Entrar y moverse

**Fecha.** 2026-11-18

Todas las pantallas comparten la misma estructura:
- **Menú lateral:** seis entradas (Dashboard, Inventario, Alertas, Reportes, Predicciones y Recomendaciones), que ven los tres roles. Abajo están el nombre y el rol de la persona, «Cambiar contraseña» y «Cerrar sesión».
- **Barra superior:** muestra la página y la versión de la aplicación.
- **Selector de ubicación:** arriba a la derecha, para el gerente y el administrador de bodega. El administrador de sucursal no lo tiene: en su lugar ve una etiqueta con su sucursal.
- **Fecha de los datos:** siempre a la vista.

**También se dice.** Menú, pantallas, cambiar de sucursal, selector de ubicación, cómo elijo la sucursal, cerrar sesión, salir, versión de la aplicación.

## Cambiar la contraseña

**Sección.** Parte II · 12.1 Entrar y moverse

**Fecha.** 2026-10-08

«Cambiar contraseña» está abajo en el menú lateral. Abre un formulario con tres campos: la contraseña actual, la nueva y su confirmación.

La nueva debe:
- tener 8 caracteres o más;
- ser distinta de la actual;
- coincidir con su confirmación.

**También se dice.** Cambiar la clave, nueva contraseña, cambiar mi contraseña, actualizar la contraseña, requisitos de la contraseña.

## El Dashboard

**Sección.** Parte II · 12.2 Dashboard

**Fecha.** 2026-10-08

Responde «¿cómo va el negocio y qué está en riesgo?». Es la primera pantalla que se abre y la única que mezcla ventas, inventario y alertas. Muestra:
- **cuatro tarjetas:** ventas del día, ventas del mes, productos en riesgo (Bajo + Crítico) y stock valorizado;
- **la tendencia de ventas de los últimos 30 días,** con el promedio móvil de 7 días («MA 7d») que suaviza los altibajos;
- **el semáforo de inventario;**
- **los cinco productos que más valor vendieron en el mes;**
- **las alertas activas por urgencia y tipo.**

El selector de ubicación cambia todas las cifras.

**También se dice.** Dashboard, inicio, pantalla principal, tarjetas, qué muestra el dashboard, resumen del negocio, tendencia de ventas, top de productos.

## Variación de las ventas del día y del mes

**Sección.** Parte II · 12.2 Dashboard

**Fecha.** 2026-10-08

Las tarjetas comparan contra periodos distintos:
- **Ventas del día:** contra el mismo día de la semana anterior.
- **Ventas del mes:** contra el mes calendario anterior.

Las ventas incluyen el IVA.

**También se dice.** Porcentaje de variación, comparado con la semana pasada, ventas del día, ventas del mes, IVA, por qué sube o baja el porcentaje.

## Stock valorizado

**Sección.** Parte II · 12.2 Dashboard

**Fecha.** 2026-10-08

El stock valorizado es la suma de stock × precio de venta base del catálogo. Es a precio de venta, no a costo, y por eso es más alto que el valor a costo. Los productos con stock negativo restan.

Es la misma cifra que muestra Reportes en «Inventario valorizado».

**También se dice.** Stock valorizado, valor del inventario, por qué es tan alto, a precio de venta, a costo, inventario valorizado, cuánto vale el inventario.

## El Dashboard de la Bodega Central

**Sección.** Parte II · 12.2 Dashboard

**Fecha.** 2026-10-08

Con la Bodega Central elegida, el Dashboard trae solo dos tarjetas: productos en riesgo y stock valorizado. Además avisa «La Bodega Central no vende: las ventas se ven por sucursal». No muestra la tendencia ni el top de productos. Sí muestra el semáforo y las alertas de la Bodega.

**También se dice.** Dashboard de la bodega, bodega central en el dashboard, por qué la bodega no tiene ventas, la bodega no vende.

## La pantalla de Inventario

**Sección.** Parte II · 12.3 Inventario y su detalle

**Fecha.** 2026-11-18

Responde «¿cuánto hay de cada producto y para cuántos días alcanza?». Es la lista completa de la foto, con una fila por producto y ubicación.

**Filtros:**
- ubicación;
- estado (Todos, OK, Bajo, Crítico o Inconsistencia);
- categoría;
- búsqueda por nombre o código, con Enter o la lupa.

**Columnas:** Producto, Categoría, Sucursal, Stock, Stock Bodega, Reorden, Cobertura y Estado. «Stock Bodega» dice cuánto tiene la Bodega Central del mismo producto, es decir, si hay de dónde trasladar. En el celular, cada producto se muestra como una tarjeta con el stock y el estado a la vista.

**También se dice.** Inventario, cómo filtro el inventario, filtrar por categoría, buscar un producto, filtrar por estado, columnas, stock bodega, lista de productos.

## Cómo leer la cobertura en Inventario

**Sección.** Parte II · 12.3 Inventario y su detalle

**Fecha.** 2026-10-08

La cobertura se lee en días («d»). Hay tres casos que conviene reconocer:
- **«Sin ventas»:** el producto no tiene ventas registradas en esa sucursal, así que no se puede calcular para cuántos días alcanza.
- **Una cobertura muy alta:** puede ser real, si el producto se vende muy poco. No es un error.
- **«—»:** las inconsistencias no tienen cobertura.

Los productos por kilo llevan un decimal.

**También se dice.** Sin ventas, qué significa sin ventas, cobertura muy alta, días de cobertura, guion en la cobertura, productos por kilo.

## El detalle de un producto

**Sección.** Parte II · 12.3 Inventario y su detalle

**Fecha.** 2026-10-08

**Abrir y cerrar.** El detalle se abre con un clic en el nombre del producto. Se cierra con la X, con la tecla Escape o con un clic fuera del panel.

**Qué muestra.**
- El encabezado: producto, categoría, ubicación, código, cómo se vende (unidad o kilo) y estado.
- Seis datos: stock actual, stock en la Bodega, stock mínimo, stock máximo, punto de reorden y cobertura.
- El proveedor y las fotos de inventario.

El proveedor es un dato simulado, porque los reportes de ventas no traen compras.

**También se dice.** Detalle del producto, ficha del producto, abrir un producto, ver el proveedor, panel del producto.

## Stock mínimo, máximo y punto de reorden

**Sección.** Parte II · 12.3 Inventario y su detalle

**Fecha.** 2026-10-08

Estos tres números no los definió el negocio: son aproximaciones que salen de la venta diaria promedio.
- **Mínimo:** 3 días de venta.
- **Punto de reorden:** 7 días de venta.
- **Máximo:** 30 días de venta.

Son la política de inventario aproximada que se usó al armar la bodega de datos.

**También se dice.** Stock mínimo, stock máximo, punto de reorden, reorden, de dónde salen, quién definió el mínimo, cómo se calcula el mínimo.

## La pantalla de Alertas

**Sección.** Parte II · 12.4 Alertas

**Fecha.** 2026-11-18

Responde «¿qué necesita atención primero?». Tiene dos pestañas: «Por reglas» y «Con IA».

**Arriba:**
- la ubicación y el botón «Actualizar»;
- un resumen con el total, las críticas, las altas y las medias.

**Filtros:** por tipo y por urgencia, con casillas para elegir varios valores. Para ver solo las de stock crítico, por ejemplo, se marca ese tipo.

**Cada alerta:** producto, ubicación, tipo, urgencia y una frase que dice qué pasa. La lista va por páginas, con las críticas arriba.

**También se dice.** Alertas, cómo filtro las alertas, ver solo las críticas, filtrar por tipo, stock crítico, pestaña por reglas, actualizar alertas.

## La pantalla de Reportes

**Sección.** Parte II · 12.5 Reportes

**Fecha.** 2026-10-08

Responde «¿cuánto se vendió, contra qué periodo y en qué categorías?». Por defecto muestra el mes de la última venta.

**Filtros:**
- atajos Mes, Trimestre, Año y Todo;
- fechas Desde y Hasta;
- agrupación por día, semana o mes;
- categoría.

El administrador de sucursal queda fijo en la suya.

**Contenido:**
- cuatro indicadores: valor vendido, margen, cantidad y transacciones;
- ventas por periodo y la comparativa con el periodo anterior;
- la distribución por categorías;
- la tendencia por sucursal;
- el inventario valorizado.

**También se dice.** Reportes, reporte de ventas, ventas por categoría, margen, transacciones, cambiar el periodo, ver un año, agrupar por semana.

## Comparar con el periodo anterior

**Sección.** Parte II · 12.5 Reportes

**Fecha.** 2026-10-08

Reportes y el Dashboard pueden mostrar porcentajes distintos para el mismo mes, y los dos son correctos, porque comparan contra periodos distintos:
- **Reportes** compara el periodo elegido con los mismos días inmediatamente anteriores.
- **El Dashboard** compara con el mes calendario anterior.

**También se dice.** Periodo anterior, comparativa, por qué el porcentaje es distinto, no coincide con el dashboard, diferencia entre dashboard y reportes, comparar ventas.

## Huecos en las ventas y «Sin sucursal»

**Sección.** Parte II · 12.5 Reportes

**Fecha.** 2026-10-08

**Los huecos.** En los primeros años de datos hay meses sin ventas cargadas y otros con muy pocas. Con el atajo «Todo» se ven como valles en las gráficas. No son errores de la pantalla: son huecos de los datos originales.

**«Sin sucursal».** Con los atajos «Año» y «Todo» aparece también una línea «Sin sucursal»: son las ventas sin terminal asignada, de la facturación electrónica.

**También se dice.** Meses sin ventas, huecos, valles en la gráfica, por qué no hay ventas, sin sucursal, años sin datos, faltan datos.

## La pantalla de Predicciones

**Sección.** Parte II · 12.6 Predicciones

**Fecha.** 2026-10-08

Responde «¿cuánto se venderá de este producto en esta sucursal en los próximos 15 días hábiles, y cuánto me queda?». Se usa en tres pasos:
1. Buscar el producto por nombre, familia o código. La lista muestra los primeros resultados: si son muchos, hay que escribir más para acotar.
2. Elegir la sucursal. Solo aparecen las sucursales que venden: la Bodega Central no.
3. Leer las tarjetas y la gráfica.

**Tarjetas:**
- demanda prevista y límite de negocio;
- riesgo según el pronóstico;
- interpretación y rama del modelo;
- stock actual y cobertura del inventario.

**También se dice.** Predicciones, cómo veo el pronóstico, pronóstico de un producto, buscar producto en predicciones, elegir sucursal, cuánto se va a vender.

## Cuando Predicciones no da pronóstico

**Sección.** Parte II · 12.6 Predicciones

**Fecha.** 2026-10-08

**Sin historia suficiente.** Si el producto no tiene suficientes días con venta en esa sucursal, Predicciones no muestra pronóstico. En su lugar dice el motivo, con el botón «Reintentar»: «No hay historia suficiente…». Es una respuesta correcta, no una falla.

**Sin ventas recientes.** Si el producto no vendió en una temporada, la gráfica lo avisa.

**La Bodega Central.** No aparece en el selector de sucursal, porque no vende.

**También se dice.** No hay historia suficiente, Predicciones no muestra nada, sin pronóstico en predicciones, reintentar, por qué no sale la predicción, no vendió.

## Cómo leer la gráfica de Predicciones

**Sección.** Parte II · 12.6 Predicciones

**Fecha.** 2026-10-08

**Qué dibuja:**
- **Barras azules:** lo vendido en cada una de las últimas ocho ventanas de 15 días hábiles, sin devoluciones.
- **Barra clara con borde punteado:** el pronóstico.
- **Línea naranja punteada:** el límite de negocio.
- **Línea verde:** el stock actual.

No hay bandas ni intervalos. Las ventanas anteriores a la primera venta del producto valen cero, y eso no quiere decir que se vendió cero.

**También se dice.** Gráfica de predicciones, línea naranja, línea verde, barras azules, barra punteada, qué significa la línea, leer la gráfica.

## La pantalla de Recomendaciones

**Sección.** Parte II · 12.7 Recomendaciones

**Fecha.** 2026-10-08

Responde «¿qué traslado o compra se sugiere, y para cuándo?».

**Pestañas.** Tiene dos, Compras y Transferencias, y calcula solo la que está abierta.

**Filtros.** Categoría, urgencia y búsqueda por nombre o código. El selector de ubicación incluye la Bodega Central para el gerente y el administrador de bodega.

**La primera consulta.** Calcula las recomendaciones de toda la red y tarda, del orden de medio minuto. Los filtros siguientes responden en menos de un segundo. Las alertas con IA comparten ese cálculo.

**También se dice.** Recomendaciones, por qué tarda, demora la primera vez, compras sugeridas, pantalla de compras, pestañas, se demora en cargar.

## Las columnas de Compras

**Sección.** Parte II · 12.7 Recomendaciones

**Fecha.** 2026-10-08

La tabla de compras a proveedor tiene una fila por producto y destino:
- **Producto:** nombre, código y categoría.
- **Destino:** la sucursal o la Bodega Central.
- **Grupo:** semanal (martes) o quincenal.
- **Cantidad:** en unidades o en kilos, nunca sumados.
- **Urgencia.**
- **Días hasta agotarse.**
- **Pedido:** la fecha del pedido.
- **Llega:** la llegada a la sucursal y, en las líneas de la Bodega, también la llegada a la Bodega.
- **«Llega tarde».**
- **Motivo:** «Reposición» o «Stock negativo».

**También se dice.** Columnas de compras, tabla de compras, destino, grupo, días hasta agotarse, motivo, qué significa cada columna.

## Compras de una sucursal y «Necesidad vía la Bodega»

**Sección.** Parte II · 12.7 Recomendaciones

**Fecha.** 2026-10-08

Con una sucursal elegida, Compras muestra dos tipos de línea:
- sus compras directas;
- las compras a la Bodega en las que esa sucursal participa.

La tarjeta «Necesidad vía la Bodega» dice cuánto de esas compras es para la sucursal. En esas líneas, la urgencia y los días se calculan desde la sucursal, pero la cantidad es la de toda la compra a la Bodega.

**También se dice.** Necesidad vía la bodega, necesidad de la sucursal, por qué la cantidad es tan grande, compras de mi sucursal.

## La pestaña Transferencias

**Sección.** Parte II · 12.7 Recomendaciones

**Fecha.** 2026-10-08

Muestra los traslados sugeridos. Arriba, un resumen. Debajo, la tabla con:
- producto;
- origen, con la marca «Bodega» cuando sale de la Bodega Central;
- destino;
- cantidad;
- urgencia (Urgente, Alta, Normal o Vigilancia);
- días hasta agotarse;
- llegada;
- «Llega tarde».

Los traslados salen antes que las compras: lo que no cubren pasa a Compras.

**También se dice.** Transferencias, traslados, pestaña transferencias, para qué sirve, vigilancia, origen y destino, ver los traslados.

## Exportar a CSV y abrirlo en Excel

**Sección.** Parte II · 12.7 Recomendaciones

**Fecha.** 2026-10-08

**Qué descarga.** El botón «Exportar CSV» descarga todas las filas que pasan los filtros y la búsqueda, no solo la página visible. El nombre del archivo dice el tipo, la ubicación y la fecha de la foto.

**El formato.** Está pensado para Excel con la configuración regional de Colombia:
- texto UTF-8 con marca de orden de bytes, para que se vean las tildes;
- columnas separadas por punto y coma;
- coma decimal;
- fechas en formato ISO;
- la unidad en su propia columna.

**Si Excel lo muestra todo en una sola columna:** pasa con otra configuración regional. Se abre con «Datos → Desde texto/CSV».

**También se dice.** Exportar, descargar, CSV, Excel, abrir en Excel, todo en una columna, descargar las compras, bajar el archivo, tildes raras.

## Esperas, avisos y errores

**Sección.** Parte II · 12.9 Esperas, avisos y errores

**Fecha.** 2026-10-08

Una pantalla siempre dice qué está pasando. Cuando algo tarda o falla, no queda en blanco: muestra un mensaje en español. En los errores aparece el botón «Reintentar».

**También se dice.** Error, no carga, se quedó cargando, reintentar, mensaje de error, la pantalla no responde, aviso.

## Celular, teclado y accesibilidad

**Sección.** Parte II · 12.10 Pantallas pequeñas y accesibilidad

**Fecha.** 2026-11-18

**En el celular y en pantallas pequeñas.** La aplicación se adapta al ancho de la pantalla:
- el menú lateral se oculta tras el botón «Abrir menú»;
- las tarjetas pasan a una columna;
- Inventario se muestra en tarjetas.

**Para todas las personas.**
- El estado nunca depende solo del color: lleva texto y símbolo.
- Se puede usar con el teclado. El primer Tab ofrece «Saltar al contenido».
- Los lectores de pantalla reciben las etiquetas y los errores.

**También se dice.** Celular, teléfono, móvil, tableta, pantalla pequeña, accesibilidad, teclado, lector de pantalla, abrir menú, usar desde el celular.

# Parte III · Guía de Vera

## Qué se le puede preguntar a Vera

**Sección.** Parte III · 16.1 Qué se le puede preguntar

**Fecha.** 2026-11-18

Vera responde sobre los mismos datos que las pantallas:
- el inventario y su estado;
- las alertas, por reglas y con IA;
- las ventas: el historial, los productos más vendidos y un mes concreto;
- el pronóstico;
- las compras y los traslados sugeridos.

También responde qué significa un término del glosario del negocio y cómo se usa la aplicación, con esta guía. Es de solo lectura: no cambia nada en el sistema.

Al abrirla, ofrece preguntas rápidas según el rol, y en cada pantalla, tres preguntas sobre lo que se está viendo.

**También se dice.** Qué le puedo preguntar a Vera, qué sabe Vera, para qué sirve Vera, preguntas rápidas, qué hace el asistente, ejemplos de preguntas.

## Consejos para preguntarle a Vera

**Sección.** Parte III · 20.7 Lo que ve cada rol

**Fecha.** 2026-10-28

**Lo que puede responder.** Vera responde lo mismo que cada rol ve en las pantallas.

**Cómo preguntar mejor:**
- Nombrar el producto y la sucursal como aparecen en el sistema: así encuentra mejor.
- Si la respuesta no es lo que se buscaba, reformular en una pregunta nueva y más precisa, en vez de insistir.
- Para un tema nuevo, empezar con «Nueva conversación».
- Para decidir, abrir la pantalla que dice «Consultado:» y comprobar la cifra.

**También se dice.** Cómo pregunto, consejos, Vera no entiende, preguntar mejor, cómo le hablo a Vera, no me entiende.

## Cuánto tarda Vera

**Sección.** Parte III · 16.3 Lo que hay que tener presente

**Fecha.** 2026-11-18

**Lo normal.** Vera responde en pocos segundos.

**Cuando tarda más.** Una pregunta que compara varias sucursales, o la primera después de un rato sin uso, puede tardar más: a veces uno o dos minutos. Si tarda, la ventana avisa «Está tardando más de lo normal…», dice en qué va y permite detenerla.

**También se dice.** Por qué se demora Vera, tarda mucho, lento, cuánto tarda, se queda pensando, demora en contestar.

## De dónde saca Vera los datos

**Sección.** Parte III · 17.2 Las consultas: los mismos datos que las pantallas

**Fecha.** 2026-10-28

Vera consulta el Core API con las mismas consultas que usan las pantallas y con el permiso de quien pregunta: no puede ver más que esa persona. Si una respuesta necesita varias consultas, por ejemplo buscar el producto y después su pronóstico, las hace en orden antes de redactar.

No escribe consultas directas a la base de datos. Así, los permisos los revisa el Core API, como en las pantallas.

**También se dice.** De dónde saca los datos Vera, Vera ve todo, permisos de Vera, cómo consulta, base de datos, Vera puede ver otras sucursales.

## El glosario y la guía en Vera

**Sección.** Parte III · 17.3 El glosario del negocio

**Fecha.** 2026-11-18

Para preguntas como «¿qué significa el rojo en el semáforo?» o «¿cómo descargo las compras?», Vera busca en el glosario del negocio y en esta guía de uso. La búsqueda es por palabras: da más peso a las palabras poco frecuentes y a las que aparecen en el título o en los sinónimos.

Si nada cubre la pregunta, la búsqueda no devuelve resultados y Vera dice que no tiene esa información, en vez de improvisar. Cuando responde con el glosario o la guía, cita la fuente o la sección.

**También se dice.** Glosario, guía, cómo sabe Vera, búsqueda, Vera no sabe, no tiene la información, de dónde saca la explicación, fuente.

## Las instrucciones que sigue Vera

**Sección.** Parte III · 17.4 Las instrucciones por rol

**Fecha.** 2026-10-28

Antes de cada pregunta, Vera recibe instrucciones fijas: una parte común y otra según el rol. Entre otras cosas, debe:
- usar siempre una consulta para dar una cifra, y decir el total cuando la consulta lo trae;
- poner solo los filtros que la pregunta nombra: si no menciona una sucursal, consulta todas las que ve la persona;
- pedir aclaración si la pregunta es ambigua, por ejemplo un producto que coincide con muchos;
- responder con una frase fija cuando la pregunta está fuera de alcance, no hay datos o falta permiso.

**También se dice.** Instrucciones de Vera, reglas de Vera, por qué Vera pregunta cuál, aclaración, fuera de alcance, frase fija.

## Cómo comprueba Vera sus cifras

**Sección.** Parte III · 17.5 La verificación antes de mostrar la respuesta

**Fecha.** 2026-11-18

Cuando el modelo termina de redactar, Vera no muestra el texto de inmediato: lo retiene y lo revisa.
- Cada número debe estar en los datos consultados.
- Si la consulta trajo un total, la respuesta debe decirlo.
- No puede decir que «no hay» algo sin haberlo consultado.
- No puede hablar de «la mayoría» mirando solo una parte de la lista.

Si algo falla, le pide al modelo que corrija una vez. Si vuelve a fallar, responde solo con las tablas consultadas, sin redactar. Al final agrega la fecha de los datos si el texto no la dice.

**También se dice.** Cifras inventadas, Vera inventa, cómo sé que es verdad, verificación, comprobar las cifras, confiar en Vera, alucinación.

## La memoria de la conversación

**Sección.** Parte III · 17.6 La conversación y su memoria

**Fecha.** 2026-10-28

**Lo que recuerda.** Vera recuerda las preguntas y respuestas recientes de la misma conversación. Por eso entiende «¿y en la otra sucursal?» después de una pregunta.

**Sus límites.**
- La memoria tiene un tamaño fijo: cuando la conversación crece, se olvidan primero los turnos más viejos.
- Cada mensaje admite hasta 2.000 caracteres.

**Dónde se guarda.** En ninguna parte: la conversación vive solo en la ventana. Se borra al cerrar sesión o al pulsar «Nueva conversación».

**También se dice.** Memoria, Vera recuerda, se acuerda de lo anterior, historial, se guardan las conversaciones, conversación larga, límite de caracteres.

## Abrir Vera

**Sección.** Parte III · 20.1 Abrir Vera

**Fecha.** 2026-11-18

**Cómo abrirla.** Con el botón redondo abajo a la derecha, presente en todas las pantallas, o con el atajo Alt+V.

**Cómo se ve.** La ventana flota sobre la página, que se puede seguir usando detrás. La conversación se conserva al cambiar de pantalla.

**El encabezado.** Dice «Pregúntale a tu inventario» y tiene tres botones: «Nueva conversación» (+), maximizar y cerrar. Debajo están el saludo y las preguntas rápidas del rol.

**Cómo escribir.** Enter envía; Mayús+Enter agrega una línea.

**También se dice.** Abrir Vera, dónde está Vera, botón de Vera, atajo, cerrar Vera, nueva conversación, empezar de nuevo, borrar la conversación.

## Las partes de una respuesta de Vera

**Sección.** Parte III · 20.2 Una respuesta, parte por parte

**Fecha.** 2026-10-28

Cada respuesta trae lo necesario para comprobarla:
- el texto, con la fecha de los datos;
- la tabla con lo que trajo la consulta. Se pliega con la flecha del título, y «CSV» la descarga para Excel;
- «Consultado:», con las consultas hechas, la fecha de los datos y cuánto tardó;
- «Copiar», que copia el texto para pegarlo en un correo o un chat;
- preguntas sugeridas para seguir, que se envían con un clic.

**También se dice.** Copiar la respuesta, consultado, descargar la tabla, CSV de Vera, preguntas sugeridas, mandar por correo, partes de la respuesta.

## Tarjetas y gráficas en las respuestas de Vera

**Sección.** Parte III · 20.2 Una respuesta, parte por parte

**Fecha.** 2026-11-18

Cuando conviene, Vera muestra lo que consultó en tres partes:
- **Tarjetas** con las cifras destacadas. El color ayuda (verde, amarillo o rojo), pero la etiqueta siempre dice qué es.
- **Una gráfica:**
  - barras por periodo para las ventas, o líneas si son muchos periodos;
  - barras horizontales para los rankings;
  - barras apiladas para el estado del inventario o las alertas por sucursal;
  - stock frente a demanda en la ficha de un producto.
- **La tabla,** plegada debajo. Se abre con su título y tiene el botón «CSV».

Al pasar el mouse sobre la gráfica se ven las cifras exactas. Las cifras completas siempre están en la tabla.

**También se dice.** Tarjetas, gráficas, gráfico, infografía, por qué la tabla está cerrada, ver la tabla, colores de las tarjetas, cómo leer la gráfica de Vera.

## Ficha de un producto y precios en Vera

**Sección.** Parte III · 16.1 Qué se le puede preguntar

**Fecha.** 2026-11-18

**La ficha.** A la pregunta «¿cómo está el producto…?», cuando se piden varias cosas a la vez, Vera responde con la ficha del producto:
- precio, costo y margen del catálogo;
- stock y estado en cada ubicación;
- demanda esperada para los próximos 15 días hábiles;
- alertas de inventario;
- ventas de los últimos 30 días con su margen.

**Precios y márgenes.**
- El precio y el costo del catálogo son los de la última venta registrada.
- El margen realizado sale de las ventas del periodo.
- Con una categoría, Vera arma el reporte desglosado por producto, de mayor a menor valor vendido.

**También se dice.** Ficha del producto, estado general de un producto, precio, costo, margen, de dónde sale el precio, reporte por categoría, margen realizado.

## El pronóstico y la fecha de hoy en Vera

**Sección.** Parte III · 17.2 Las consultas: los mismos datos que las pantallas

**Fecha.** 2026-11-18

**La ventana.** Cada pronóstico dice qué días hábiles cubre, desde cuándo y hasta cuándo, y cuánto se espera vender en promedio por día hábil.

**Si los datos no llegan hasta hoy,** Vera lo dice: el pronóstico usa los datos hasta la última fecha cargada. Para que cubra desde hoy, hay que cargar las ventas y el inventario hasta hoy.

**Para una fecha elegida.** También se le puede pedir el pronóstico desde una fecha («desde el lunes», «desde el mes pasado»), para un día («para el viernes», «mañana») o para un rango («la próxima semana», «hasta fin de mes», «en diciembre»).
- **Si la fecha ya pasó,** Vera pronostica con lo que se sabía el día anterior y lo compara con lo que se vendió de verdad.
- **Un día o un rango es una aproximación:** se reparte el pronóstico de 15 días hábiles, o se encadenan varias ventanas.

**Productos de temporada.** El modelo no usa el calendario: pronostica con la historia reciente. Un producto que solo se vende en una época del año, sin ventas en los meses recientes, puede salir en cero para su temporada.
- Por eso Vera muestra también lo vendido en las mismas fechas del año anterior.
- Si el pronóstico queda muy por debajo de eso, avisa que el modelo no considera la temporada.
- Esa cifra del año anterior es una referencia, no un pronóstico.

**También se dice.** Pronóstico de hoy, cuánto se vende hoy, está actualizado, datos de hoy, por día, ventana del pronóstico, desde cuándo pronostica, pronóstico para una fecha, para un día, para un rango, comparar el pronóstico con lo vendido, qué tan bueno fue el pronóstico, pronóstico en cero, producto de temporada, año anterior.

## Detener una respuesta

**Sección.** Parte III · 20.3 Mientras piensa, y cómo detenerla

**Fecha.** 2026-10-28

**En qué va.** Mientras trabaja, la ventana dice en qué va: «Analizando tu pregunta…», «Consultando…», «Verificando…». Si tarda, muestra un aviso que explica por qué.

**Detener.** El botón «Detener» corta la respuesta. Lo que alcanzó a llegar queda marcado como «Detenida».

**También se dice.** Detener, parar, cancelar la respuesta, se está demorando, cortar, Vera no termina.

## Cuando Vera dice que no hay permiso

**Sección.** Parte III · 20.4 Cuando falta permiso

**Fecha.** 2026-10-28

Vera no decide los permisos: los aplica el Core API a cada consulta, como en las pantallas. Si se pregunta por una ubicación que el rol no puede ver:
- aparece el aviso rojo «Tu rol no tiene permiso para parte de esta consulta», con la frase fija de Vera;
- «Consultado:» dice qué consulta se rechazó y por qué.

**También se dice.** Sin permiso, no tengo permiso, por qué no me deja, aviso rojo, otra sucursal, Vera no me responde sobre otra sucursal.

## Tablas largas en Vera

**Sección.** Parte III · 20.5 Tablas largas y la ventana maximizada

**Fecha.** 2026-10-28

Las consultas de Vera traen las primeras 10 filas y el total («Se muestran 10 de …»). La lista completa está en la pantalla correspondiente, y «CSV» descarga la tabla.

Para tablas anchas, la ventana se maximiza: la conversación se lee en una columna cómoda y la página de atrás queda inactiva hasta volver.

**También se dice.** Solo muestra diez, tabla incompleta, ver todas las filas, maximizar, tabla ancha, faltan filas.

## Vera en el celular y con el teclado

**Sección.** Parte III · 20.6 En el celular, y para todas las personas

**Fecha.** 2026-10-28

**En el celular.** En pantallas pequeñas, Vera ocupa toda la pantalla, y la tabla se desliza de lado cuando no cabe.

**Con el teclado.** Al abrirla, el foco va al campo de la pregunta. Escape cierra la ventana y devuelve el foco al botón.

**Accesibilidad.** Los lectores de pantalla anuncian cada respuesta nueva. Vera respeta la preferencia de reducir el movimiento.

**También se dice.** Vera en el celular, móvil, teclado, Escape, lector de pantalla, accesibilidad de Vera.

## Las alertas con IA

**Sección.** Parte III · 21.1 Las cifras de hoy

**Fecha.** 2026-10-28

Las alertas con IA miran hacia adelante con el pronóstico. Hay dos tipos:
- **riesgo de desabastecimiento:** el stock no alcanza para lo que se espera vender;
- **sobrestock previsto:** sobra mucho frente a lo que se espera vender.

Cada riesgo dice qué hacer, con la lógica de traslados primero y compras después: comprar, trasladar o las dos cosas. Advierten cuando el traslado llegaría tarde. Algunas coinciden con las alertas por reglas («También por reglas») y otras solo las ve el pronóstico. La cantidad y la fecha de cada compra están en Recomendaciones.

**También se dice.** Alertas con IA, alertas de inteligencia artificial, riesgo de desabastecimiento, sobrestock, qué son las alertas con IA, diferencia con las alertas por reglas.

## La pestaña «Con IA» de Alertas

**Sección.** Parte III · 21.2 En la pantalla de Alertas

**Fecha.** 2026-10-28

La pestaña «Con IA» se consulta solo al abrirla. La primera vez después de reiniciar el sistema puede tardar, porque comparte los cálculos con Recomendaciones.

**Arriba:** tarjetas de resumen con el total, el riesgo de desabastecimiento, el sobrestock previsto y «También por reglas».

**Filtros:** tipo, urgencia, origen y categoría, con casillas.

**Cada alerta:** producto, sucursal, tipo, la acción sugerida y el detalle con el stock, el pronóstico y los días que alcanza. La marca «IA» la distingue de las alertas por reglas.

**También se dice.** Pestaña con IA, por qué tarda la pestaña con IA, filtros de alertas con IA, marca IA, acción sugerida.

## Preguntarle a Vera desde una alerta

**Sección.** Parte III · 21.3 De una alerta a una pregunta

**Fecha.** 2026-10-28

Cada alerta tiene el ícono de Vera. Al pulsarlo, abre Vera con una pregunta ya escrita sobre ese producto en esa sucursal:
- **en una alerta por reglas:** cómo está su inventario;
- **en un riesgo con IA:** si el stock alcanza para los próximos 15 días hábiles;
- **en un sobrestock previsto:** cuál es su pronóstico.

Sirve para entender una alerta sin cambiar de pantalla.

**También se dice.** Ícono de Vera en la alerta, preguntar desde una alerta, para qué sirve el ícono, botón de Vera en las alertas, pregunta automática.
