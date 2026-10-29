# Glosario de InventAI/o

Términos y reglas de InventAI/o en lenguaje sencillo, para quienes usan la aplicación, para el equipo y para el asistente (INV-31). Tiene dos partes:

- **Parte I · Negocio:** el inventario, las alertas, las compras, los traslados y los indicadores, como los ve la aplicación.
- **Parte II · Pronóstico y modelos:** las técnicas y los términos del análisis de datos y del modelado de demanda (docs/METODOLOGIA-EDA-MODELADO.md y los cuadernos 01 a 15).

Cada término es una sección `##` con:
- **Qué es:** el término en palabras sencillas.
- **Regla** (o **En el proyecto**): lo que aplica el sistema.
- **Ejemplo:** con la foto de inventario del 31 de diciembre de 2025. Si dice «ilustrativo», las cifras son inventadas para explicar la regla.
- **Fuente:** el código o el documento de donde sale.
- **También se dice:** las palabras con que la gente lo pregunta.

Las cifras de las reglas se comprueban contra el código en las pruebas (`nlp_agent/tests/test_conocimiento.py`), para que no se desactualicen.

**Cómo lo usa el agente:** consulta este documento con la herramienta `buscar_en_glosario`, y cada sección es un fragmento. `nlp_agent/conocimiento/corpus.json` se genera desde aquí con `python -m conocimiento.construir` (desde `nlp_agent/`).

# Parte I · Negocio

## Foto de inventario

**Qué es.** Los datos de stock son una foto: el inventario tal como estaba en una fecha de corte. La foto vigente es la del **31 de diciembre de 2025**. Las cifras de stock, semáforo, alertas, compras y traslados son a esa fecha y no se actualizan solas.

**Regla.** El stock disponible es el real del sistema de inventario. El mínimo, el máximo, el punto de reorden y los días de cobertura se calculan con la política de inventario a partir de las ventas reales.

**Ejemplo.** «ARROZ DIANA *500 GR tiene 355 unidades en PRINCIPAL» quiere decir que tenía 355 unidades el 31 de diciembre de 2025.

**Fuente.** Carga de la bodega (`etl_real/construir_fact_inventario_real.py`).

**También se dice.** Corte, fecha de los datos, ¿de cuándo son los datos?, ¿están actualizados?, último inventario.

## Semáforo de inventario

**Qué es.** Un color por producto y ubicación que dice qué tan bien está el stock según los días de cobertura.

**Regla.**
- **Verde (OK):** alcanza para 7 días o más.
- **Amarillo (bajo):** alcanza para 3 días o más, pero menos de 7.
- **Rojo (crítico):** alcanza para menos de 3 días, incluido el stock en cero.
- **Morado (inconsistencia):** el stock es negativo, sin importar la cobertura; hay que verificar el conteo.

**Ejemplo.** En LA 21, CERVEZA ANDINA LATA 269 SIXPACK tenía 20 unidades con 0,8 días de cobertura: rojo. AGUARDIENTE AMARILLO MANZANARES * 1000 tenía 3,0 días: amarillo. En PRINCIPAL, ARROZ DIANA *500 GR tenía 17,9 días: verde.

**Fuente.** Regla del semáforo del Core API (`api/core/semaforo.py`, INV-26).

**También se dice.** Rojo, amarillo, verde, morado, color, estado del producto, crítico, bajo, ok, en riesgo, se va a acabar.

## Días de cobertura

**Qué es.** Para cuántos días alcanza el stock si se sigue vendiendo al ritmo de siempre.

**Regla.** Cobertura = stock ÷ venta diaria promedio. La venta diaria promedio es lo vendido (sin devoluciones) desde la primera hasta la última venta del producto en esa sucursal, dividido entre los días de ese periodo. Si el producto nunca se vendió allí, la cobertura es 999 (sin límite). En la Bodega Central se usa la venta de toda la red, porque la bodega no vende.

**Ejemplo.** ARROZ DIANA *500 GR en PRINCIPAL: 355 unidades y una cobertura de 17,9 días, porque se venden unas 20 unidades al día.

**Fuente.** Carga de la bodega (`etl_real/construir_fact_inventario_real.py`).

**También se dice.** Cobertura, ¿para cuántos días alcanza?, días de inventario, días de stock, duración del stock.

## Stock mínimo, máximo y punto de reorden

**Qué es.** Los niveles de referencia de cada producto en cada ubicación, según su venta diaria.

**Regla.**
- **Mínimo:** 3 días de venta.
- **Punto de reorden:** 7 días de venta.
- **Máximo:** 30 días de venta.

El semáforo usa los mismos cortes de 3 y 7 días.

**Ejemplo.** ARROZ DIANA *500 GR en PRINCIPAL tiene un mínimo de 59 unidades: unos 3 días de su venta.

**Fuente.** Política de inventario de la carga (`etl_real/config.py`, `INVENTARIO_PARAMS`).

**También se dice.** Mínimo, máximo, reorden, nivel de stock, inventario de seguridad.

## Punto de pedido

**Qué es.** El momento en que conviene comprar un producto al proveedor: cuando lo que hay, más lo que ya viene en camino, no alcanza para lo que se va a vender hasta que llegue el siguiente pedido.

**Regla.**
- **Se compra** si la posición (stock más lo que ya viene) es menor que el punto de pedido.
- **El punto de pedido** es la venta esperada (la mediana del pronóstico) en los días hábiles que debe cubrir el pedido.
- **La cantidad** es la que lleva el stock hasta el nivel, que es el mayor entre la mediana y el límite alto del pronóstico para esos días. Se redondea hacia arriba.

No es lo mismo que el punto de reorden del inventario (7 días de venta).

**Ejemplo (ilustrativo).** Si en los días que cubre el pedido se espera vender 100 unidades y entre el stock y lo que viene hay 60, se compra. Si el límite alto del pronóstico es 130, se piden 70.

**Fuente.** Política de compras, INV-21 (`ml_service/compras/politicas_inv21.json`).

**También se dice.** Cuándo pedir, cuándo comprar, punto de compra, cuánto pedir, necesidad de compra.

## Calendario de pedidos

**Qué es.** Las fechas fijas en que se hacen los pedidos a los proveedores.

**Regla.**
- **Quincenal, los días 2 y 16 de cada mes:** para los productos que pasan por la Bodega Central.
- **Semanal, cada martes:** para los perecederos y los de frío, que van directo a la sucursal.
- **Si la fecha cae en un día sin operación,** el pedido pasa al siguiente día hábil.
- **El pedido llega 5 días hábiles después.** Por la Bodega, la sucursal lo recibe 2 días hábiles más tarde, con un traslado.

**Ejemplo.** Con la foto del 31 de diciembre de 2025, el siguiente pedido quincenal es el 2 de enero de 2026: esa es la fecha de pedido de las compras urgentes.

**Fuente.** Política de compras, INV-21 (`ml_service/compras/politicas_inv21.json`).

**También se dice.** Calendario, cuándo se pide, días de pedido, frecuencia de compra, pedido quincenal, pedido semanal, cuándo llega el pedido.

## Bodega Central

**Qué es.** El centro de abastecimiento. No vende al público: recibe las compras quincenales y abastece a PRINCIPAL, LA 21 y GLORIETA con traslados.

**Regla.**
- **Perecederos y frío:** no pasan por la bodega; van directo a las sucursales.
- **Cobertura y ventas de 30 días:** se calculan con la venta de toda la red.
- **Alertas:** tiene alertas de reglas (por ejemplo, stock crítico frente a la demanda de la red), pero no tiene alertas de IA ni pronóstico propio, porque no vende.
- **Quién la ve:** el gerente y el administrador de bodega ven todo. Un administrador de sucursal puede ver el stock de la bodega, pero no sus alertas.

**Ejemplo.** Al 31 de diciembre de 2025, la bodega tenía 686 alertas de reglas, 607 de ellas críticas, y 0 alertas de IA.

**Fuente.** Políticas de compras y traslados (INV-21 e INV-22) y regla de permisos (INV-25).

**También se dice.** Bodega, centro de distribución, CEDI, almacén central, ¿por qué la bodega no vende?

## Sucursales y permisos por rol

**Qué es.** Las ubicaciones y lo que cada usuario puede consultar.

**Regla.**
- **Ubicaciones:** PRINCIPAL (tipo principal), LA 21 y GLORIETA (estándar), y la Bodega Central, que solo abastece.
- **Gerente y administrador de bodega:** ven todas las ubicaciones.
- **Administrador de sucursal:** ve solo su sucursal; del stock de la bodega puede consultar, pero no sus alertas ni sus ventas.
- **Sin permiso:** el sistema responde que no se puede y no da cifras.

**Ejemplo.** El administrador de GLORIETA que pide el inventario de LA 21 recibe «Solo puede consultar su sucursal (GLORIETA)».

**Fuente.** Regla de permisos por ubicación, INV-25 (`api/core/ubicaciones.py`).

**También se dice.** Permisos, ¿qué puedo ver?, otra sucursal, acceso, roles.

## Producto perecedero y de frío

**Qué es.** Los perecederos se dañan pronto: lácteos, cárnicos, frutas y verduras, mariscos, avícolas y huevos. Los de frío necesitan cadena de frío: buena parte de los lácteos y cárnicos, y los congelados.

**Regla.**
- **Compra:** se piden cada semana (martes) y van directo a la sucursal, sin pasar por la Bodega Central.
- **Traslados entre sucursales:** un perecedero solo se mueve hacia una sucursal donde se vende. Su stock máximo deja un margen menor (25 % sobre el límite alto del pronóstico, frente al 50 % de los demás), para que no se acumule. Los de frío nunca entran a la bodega.

**Ejemplo (ilustrativo).** Una leche que requiere frío se pide el martes directo para GLORIETA; un arroz se pide el 2 o el 16 y llega a la sucursal desde la bodega.

**Fuente.** Políticas de compras y traslados, INV-21 e INV-22.

**También se dice.** Perecedero, se daña, vence, frío, refrigerado, congelado, cómo se tratan los perecederos.

## Alertas de reglas

**Qué es.** Los avisos que el sistema genera con reglas fijas sobre la foto de inventario.

**Regla.**
- **Inconsistencia de inventario (crítica):** stock negativo.
- **Stock crítico (crítica):** menos de 3 días de cobertura.
- **Stock bajo (alta):** de 3 a 7 días de cobertura.
- **Sin movimiento (media):** hay stock pero ninguna venta en 30 días. Solo en sucursales.
- **Rotación baja (media):** vende menos del 20 % de su promedio. Solo en sucursales.

**Ejemplo.** Al 31 de diciembre de 2025 había 4.452 alertas de reglas: 1.334 críticas, 386 altas y 2.732 medias. GLORIETA tenía 1.444, de ellas 243 críticas.

**Fuente.** Alertas del Core API, INV-25 (D4).

**También se dice.** Alertas, avisos, alertas críticas, sin movimiento, rotación baja, inconsistencia.

## Priorización de alertas

**Qué es.** El orden en que conviene atender las alertas.

**Regla.**
- **Primero por urgencia:** crítica, luego alta, luego media.
- **Dentro de la misma urgencia:** según la cifra que dispara la alerta, de menor a mayor. Por ejemplo, en stock crítico, primero la de menos días de cobertura; en inconsistencia, la de stock más negativo.
- **En el resumen:** las sucursales se ordenan por número de alertas críticas.
- **Alertas de IA:** el riesgo de agotarse va de menos a más días hasta agotarse.

**Ejemplo.** En el resumen del 31 de diciembre de 2025, la bodega encabeza con 607 críticas, seguida de PRINCIPAL con 297.

**Fuente.** Core API (`api/alertas/router.py`) y alertas con IA, INV-28.

**También se dice.** Priorizar, qué atiendo primero, criterio, orden de las alertas, ranking de alertas, lo más urgente.

## Alertas de IA

**Qué es.** Avisos que usan el pronóstico de ventas, no solo el stock de la foto.

**Regla.**
- **Riesgo de desabastecimiento:** el pronóstico ve que el producto se agota en 5 días hábiles o menos (crítica) o en 10 o menos (alta), con venta esperada y stock no negativo.
- **Sobrestock previsto (media):** el stock supera dos veces el máximo de la política de traslados.

Solo hay alertas de IA en las sucursales que venden, no en la Bodega Central.

**Ejemplo.** Al 31 de diciembre de 2025 había 1.587 alertas de IA: 866 de riesgo de desabastecimiento y 721 de sobrestock.

**Fuente.** Alertas con IA, INV-28.

**También se dice.** Alertas de la IA, alertas inteligentes, riesgo de agotarse, sobrestock, exceso de inventario.

## Pronóstico de demanda

**Qué es.** Cuánto se espera vender de un producto en una sucursal en los próximos 15 días hábiles. Es el único horizonte que tiene el sistema.

**Regla.**
- **Qué da:** la venta esperada (la mediana) y una «cobertura recomendada», que es el límite alto del rango.
- **Cuándo no hay:** necesita al menos 30 días con venta en esa sucursal; si no los hay, no se pronostica.
- **Qué no hace:** no simula cambios de horario, precios ni promociones.
- **Con qué modelo:** uno de tres, según el patrón de demanda del producto (ver «LightGBM» y «Patrón de demanda» en la Parte II).

**Ejemplo.** ARROZ DIANA *500 GR en PRINCIPAL: 677 unidades en 15 días hábiles, con una cobertura recomendada de hasta 1.068.

**Fuente.** Servicio de modelos y Core API (`POST /api/ml/predict`, INV-20 e INV-25).

**También se dice.** Pronóstico, predicción, cuánto voy a vender, demanda esperada, proyección.

## Días hábiles

**Qué es.** Los días en que hay operación. Todas las cuentas de pronóstico, compras y traslados se hacen en días hábiles.

**Regla.** Hacia atrás, un día hábil es un día con alguna venta en la red, es decir, que no es un hueco de calendario (domingo, festivo o un día sin reporte). Hacia adelante, los del calendario sin cierres programados (ver «Festivos y cierres programados»). 15 días hábiles son unas tres semanas.

**Ejemplo.** El historial de ventas muestra las ventas en periodos de 15 días hábiles, y el pronóstico mira los 15 días hábiles siguientes a la foto.

**Fuente.** Políticas de compras y traslados, INV-21 e INV-22, y el calendario hábil del análisis (docs/METODOLOGIA-EDA-MODELADO.md).

**También se dice.** Días hábiles, días de operación, horizonte, 15 días, hueco de calendario.

## Compras sugeridas y su urgencia

**Qué es.** Lo que el sistema recomienda pedir a los proveedores: producto, cantidad, destino (la bodega o una sucursal), urgencia y fecha de pedido.

**Regla.**
- **Urgente:** se agota en 5 días hábiles o menos.
- **Alta:** se agota en 10 o menos.
- **Normal:** lo demás.
- **Sobrante en la bodega:** si la bodega tiene sobrante, el producto se cubre con un traslado en vez de comprarlo.
- **Compras que pasan por la bodega:** la cantidad es la de toda la compra; cada sucursal tiene su parte.

**Ejemplo.** Al 31 de diciembre de 2025 había 585 líneas de compra urgentes, con fecha de pedido del 2 de enero de 2026.

**Fuente.** Recomendación de compras, INV-21.

**También se dice.** Compras, pedido sugerido, sugerido de compra, qué comprar, qué pedir al proveedor, urgencia.

## Traslados sugeridos

**Qué es.** Mover stock de donde sobra a donde falta antes de comprar: desde la Bodega Central o entre sucursales.

**Regla.**
- **Origen:** primero sale de la bodega.
- **Reparto:** se busca que las sucursales queden con una cobertura pareja.
- **Cantidad mínima:** 6 unidades o kilos.
- **Llegada:** 2 días hábiles.
- **Urgencia:** como en las compras (5 y 10 días hábiles).
- **Perecederos y frío:** los perecederos solo van a donde se venden; los de frío no pasan por la bodega.

**Ejemplo (ilustrativo).** Si GLORIETA tiene más de su máximo de un producto y LA 21 está en rojo, se sugiere trasladar la diferencia de GLORIETA a LA 21.

**Fuente.** Recomendación de traslados, INV-22.

**También se dice.** Traslados, transferencias, mover stock, despachos de la bodega, redistribuir.

## Ventas de 30 días

**Qué es.** Las unidades (o kilos) vendidas en los últimos 30 días hasta la foto, sin devoluciones. Sirve para distinguir lo que se mueve de lo que no.

**Regla.** El inventario muestra primero los productos que se venden. Entre ellos, los de menos cobertura, y a igual cobertura, los que más se venden. En la Bodega Central son las ventas de toda la red.

**Ejemplo.** ARROZ DIANA *500 GR vendió 1.814 unidades en PRINCIPAL en los 30 días anteriores al 31 de diciembre de 2025.

**Fuente.** Inventario del Core API, INV-65.

**También se dice.** Ventas del mes, ventas recientes, rotación, lo que más se vende.

## Inconsistencia de inventario

**Qué es.** Un stock negativo en la foto: el sistema registró más salidas que entradas. No es un faltante real; es un error de conteo o de registro.

**Regla.** Siempre es morado en el semáforo y una alerta crítica, sin importar la cobertura. Hay que verificar el conteo físico.

**Ejemplo.** LECHE COLANTA DESLACTOSADA *1100 tenía -3 unidades en GLORIETA. En la foto del 31 de diciembre de 2025 hay 220 inconsistencias.

**Fuente.** Regla del semáforo e INV-25 (R4).

**También se dice.** Stock negativo, inventario negativo, descuadre, morado, error de inventario.

## Categoría de producto

**Qué es.** El grupo al que pertenece cada producto del catálogo, como Lácteos, Licores, Arroz o Aseo hogar.

**Regla.** El catálogo tiene 33 categorías. El inventario, las compras sugeridas y los reportes de ventas se pueden filtrar por categoría. Una palabra como «jabón» no es una categoría: hay jabones en Aseo hogar y en Cuidado personal, así que hay que precisar el producto o la categoría.

**Ejemplo.** En LA 21 hay 64 filas de inventario de la categoría Licores en la foto del 31 de diciembre de 2025.

**Fuente.** Catálogo de productos de la bodega (`dw.dim_producto`, campo `categoria`).

**También se dice.** Categoría, familia, línea de productos, tipo de producto, sección.

## Código de producto

**Qué es.** El identificador de cada producto en el negocio, distinto de su nombre.

**Regla.** Los códigos tienen formas como P626 o 00196. El buscador de productos acepta el código además del nombre o una parte del nombre, y devuelve el código, el nombre y la categoría.

**Ejemplo.** P626 es ARROZ DIANA *500 GR; P1234 es PONQUE BIMBO CASERO *240GR.

**Fuente.** Catálogo de productos de la bodega (`dw.dim_producto`, campo `codigo_item`).

**También se dice.** Código, referencia, SKU, ítem, código del producto.

## Productos que se venden por kilo

**Qué es.** Los productos cuyas cantidades se manejan en kilos y no en unidades, como las frutas y verduras a granel.

**Regla.** De los 4.449 productos del catálogo, 64 se venden por kilo. Sus cantidades se muestran en kilos con un decimal («91,2 kg»); las de los demás, en unidades. Antes de trasladar un producto por kilo se descuenta un 10 % por la pérdida del traslado.

**Ejemplo.** El pronóstico de PAPAYA DULCINEA *KL en PRINCIPAL es de 91,2 kg en 15 días hábiles.

**Fuente.** Catálogo de productos (`dw.dim_producto`, campo `se_vende_por_kilo`) y política de traslados, INV-22.

**También se dice.** Por kilo, a granel, kilos, kg, peso.

## Ventas netas y devoluciones

**Qué es.** Las ventas que cuentan para el pronóstico, la cobertura y el historial: sin devoluciones y solo con cantidades positivas.

**Regla.** Las devoluciones se registran aparte y no suman como venta. Los indicadores del dashboard también las excluyen.

**Ejemplo.** De 2.056.210 líneas de venta en la bodega (de enero de 2022 a diciembre de 2025), 1.351 son devoluciones.

**Fuente.** Vista de ventas diarias netas de la bodega (`dw.v_ventas_diarias_netas`, `database/init.sql`).

**También se dice.** Devoluciones, ventas netas, ventas sin devoluciones, notas crédito.

## SIN_SUCURSAL

**Qué es.** Las ventas que se registraron sin la terminal de una sucursal.

**Regla.** Sus ventas sí suman en los totales del negocio. Pero no es una ubicación: no tiene inventario, no aparece en la lista de sucursales y no se puede elegir como filtro; si se pide, el sistema responde con un error de solicitud.

**Ejemplo.** En la lista de sucursales solo aparecen PRINCIPAL, LA 21, GLORIETA y la Bodega Central.

**Fuente.** Regla de permisos por ubicación, INV-25 (D7 y R2).

**También se dice.** Sin sucursal, sin terminal, ventas sin ubicación.

## Indicadores del dashboard

**Qué es.** Los números que muestra el Dashboard al entrar, con la fecha de los últimos datos.

**Regla.**
- **Ventas del día:** las del último día con ventas, comparadas con el mismo día de la semana anterior.
- **Ventas del mes:** las del mes de ese día, comparadas con el mes anterior.
- **Productos en riesgo:** cuántos productos, por ubicación, están en amarillo o rojo en el semáforo; los de stock negativo no cuentan, porque son inconsistencias.
- **Stock valorizado:** el stock de la foto multiplicado por el precio base de cada producto.

Todos respetan los permisos del rol: un administrador de sucursal ve solo los de su sucursal.

**Ejemplo.** Al 31 de diciembre de 2025 había 1.500 productos en riesgo en toda la red.

**Fuente.** Reportes del Core API (`GET /api/reportes/kpis`, `api/reportes/router.py`).

**También se dice.** KPI, indicadores, tablero, dashboard, productos en riesgo, stock valorizado, cómo vamos.

## Margen

**Qué es.** Lo que queda de una venta después de restar su costo.

**Regla.** Margen = valor de la venta − costo. Los reportes de ventas lo muestran por día, semana o mes, junto con las cantidades y el valor.

**Ejemplo (ilustrativo).** Si un producto se vendió por 10.000 pesos y costó 8.000, el margen es de 2.000 pesos.

**Fuente.** Reportes de ventas del Core API (`api/reportes/router.py`).

**También se dice.** Margen, ganancia, utilidad, rentabilidad.

## Tiempo de entrega

**Qué es.** Lo que tarda en llegar un pedido o un traslado.

**Regla.**
- **Pedido al proveedor:** llega 5 días hábiles después de hacerlo.
- **Por la Bodega Central:** la sucursal lo recibe 2 días hábiles más tarde, con un traslado.
- **Traslado:** llega en 2 días hábiles.

**Ejemplo.** Un pedido quincenal del 2 de enero de 2026 llega 5 días hábiles después a la bodega, y 2 días hábiles más tarde a la sucursal.

**Fuente.** Políticas de compras y traslados, INV-21 e INV-22.

**También se dice.** Tiempo de entrega, lead time, cuándo llega, demora del proveedor, días de llegada.

## Posición de inventario

**Qué es.** Lo que hay más lo que ya viene en camino. Es lo que se compara con el punto de pedido para decidir si se compra.

**Regla.** Posición = stock (un stock negativo cuenta como cero) + lo que ya se recibió o viene en camino.

**Ejemplo (ilustrativo).** Con 40 unidades en stock y 20 en camino, la posición es de 60 unidades.

**Fuente.** Recomendación de compras, INV-21 (`docs/INV-21-compras.md`).

**También se dice.** Posición, stock más lo que viene, inventario en tránsito, en camino.

## Cobertura recomendada

**Qué es.** El límite alto del pronóstico: lo que conviene tener para no quedarse corto en los próximos 15 días hábiles.

**Regla.** Es un cuantil de negocio del pronóstico, no la mediana. Apunta alto en los no perecederos (cuantil 0,89: mejor sobrar que faltar) y bajo en los perecederos (0,17: el sobrante se daña). Las compras usan el mayor entre la mediana y este límite.

**Ejemplo.** ARROZ DIANA *500 GR en PRINCIPAL: la venta esperada es de 677 unidades y la cobertura recomendada, de hasta 1.068.

**Fuente.** Pronóstico del Core API (`POST /api/ml/predict`) y cuantil de negocio (ver la Parte II).

**También se dice.** Cobertura recomendada, límite alto, rango del pronóstico, cuánto tener, colchón.

## Sobrante de la bodega

**Qué es.** Lo que le queda a la Bodega Central después de los traslados sugeridos.

**Regla.** Antes de comprar a un proveedor, el sistema descuenta el sobrante de la bodega. Si alcanza, el producto se cubre con un traslado en vez de comprarlo. En los productos por kilo se cuenta el 90 %, por la pérdida del traslado. Con stock negativo en la bodega, el sobrante es cero.

**Ejemplo.** De las 585 líneas de compra urgentes del 31 de diciembre de 2025, 69 se cubren con traslados desde la bodega.

**Fuente.** Recomendación de compras, INV-21, y de traslados, INV-22.

**También se dice.** Sobrante, excedente, cubrir con traslado, lo que sobra en la bodega.

## Llega tarde

**Qué es.** Una marca en un traslado o una compra cuando llega después de que el producto se agota.

**Regla.** Llega tarde si los días hasta agotarse son menos que los días hábiles que tarda en llegar; el mismo día no cuenta como tarde. El traslado o la compra se sugiere igual, con la marca.

**Ejemplo (ilustrativo).** Si un producto se agota en 1 día y el traslado tarda 2 días hábiles, llega tarde.

**Fuente.** Recomendación de traslados, INV-22 (P13).

**También se dice.** Llega tarde, no alcanza a llegar, se agota antes, llegada tardía.

## Vigilancia

**Qué es.** La urgencia de traslado de un producto que, según el pronóstico, no se va a vender en esa sucursal (venta esperada en cero).

**Regla.** Un producto en vigilancia nunca es urgente y no envía stock a otras sucursales. Solo puede recibir sobrante de la bodega, hasta el límite alto del pronóstico. Las urgencias de traslado son, en orden: urgente, alta, normal y vigilancia.

**Ejemplo.** Si el pronóstico de un producto en una sucursal es cero, esa sucursal queda en vigilancia: no envía ese producto a otras y solo puede recibir sobrante de la bodega.

**Fuente.** Recomendación de traslados, INV-22 (P14).

**También se dice.** Vigilancia, en observación, sin venta esperada.

## Producto sin pronóstico

**Qué es.** Un producto en una sucursal para el que el modelo no da pronóstico.

**Regla.** Pasa, por ejemplo, cuando no tiene al menos 30 días con venta en esa sucursal, lo mínimo que exige el modelo. Sin pronóstico no se sugiere compra ni traslado; queda como alerta «sin pronóstico» en los traslados.

**Ejemplo.** En la foto del 31 de diciembre de 2025 hay 2.762 combinaciones de producto y sucursal sin pronóstico. JABON LIQUIDO REY DOY *400 ML solo tiene pronóstico en PRINCIPAL: en LA 21 tiene 9 días con venta y en GLORIETA, 12.

**Fuente.** Servicio de modelos y recomendación de traslados, INV-22.

**También se dice.** Sin pronóstico, no hay pronóstico, historia insuficiente, producto nuevo.

## Unidades de exhibición

**Qué es.** Lo mínimo que una sucursal conserva de un producto cuando se lo trasladan a otra.

**Regla.** En un traslado, la sucursal de origen se queda con 2 unidades para exhibir; solo se mueve lo que pase de ahí.

**Ejemplo.** Una sucursal que envía un producto a otra conserva al menos 2 unidades de ese producto.

**Fuente.** Política de traslados, INV-22 (`stock_maximo.unidades_exhibicion`).

**También se dice.** Exhibición, góndola, mínimo en la sucursal, lo que queda en la tienda.

## Festivos y cierres programados

**Qué es.** Los días del calendario que cambian la operación.

**Regla.** Los cierres programados del calendario son Año Nuevo (1 de enero) y Viernes Santo: hacia adelante no cuentan como días hábiles. Los demás festivos están marcados en el calendario, y su efecto sobre la venta se mide con el efecto de calendario (Parte II). El calendario de la bodega va de 2022 a 2027.

**Ejemplo.** En 2026 los cierres programados son el 1 de enero y el 3 de abril (Viernes Santo).

**Fuente.** Calendario de la bodega (`dw.dim_tiempo`, campos `es_festivo` y `es_cierre_programado`).

**También se dice.** Festivo, feriado, cierre, qué días cierra, día cerrado, supermercado cerrado, calendario, puente.

# Parte II · Pronóstico y modelos

## Grano temporal

**Qué es.** La unidad de tiempo sobre la que se agrega una métrica: diario, semanal o mensual.

**En el proyecto.** Un grano más fino (diario) tiene más ruido pero cubre menos catálogo con confianza estadística; uno más grueso (mensual) suaviza el ruido pero pierde capacidad de reacción.

**Fuente.** Análisis y modelado (docs/METODOLOGIA-EDA-MODELADO.md, cuadernos 01 a 08).

**También se dice.** Grano, granularidad, nivel de agregación, diario, semanal, mensual.

## Hueco de calendario

**Qué es.** Un día sin ninguna venta registrada en todo el negocio.

**En el proyecto.** Se clasifica en domingo, festivo o residuo sin explicar (ni domingo ni festivo), que indica un reporte de origen faltante y no un día real sin actividad. Los días que no son huecos son los días hábiles (Parte I).

**Fuente.** Análisis de calidad y calendario (cuadernos 01, 03 y 04; calendario_habil.csv).

**También se dice.** Hueco, día sin ventas, residuo, día faltante.

## Ventana activa

**Qué es.** El rango entre la primera y la última venta real de un producto en una sucursal.

**En el proyecto.** Un producto «vivo» para el pronóstico tiene ventas recientes dentro de esa ventana; uno «muerto» (descontinuado) se excluye para no tratarlo como si siguiera activo. La venta diaria promedio de los días de cobertura se calcula sobre esta ventana.

**Fuente.** Análisis (cuadernos 01 a 04; docs/METODOLOGIA-EDA-MODELADO.md) y carga de la bodega (etl_real/construir_fact_inventario_real.py).

**También se dice.** Ventana activa, producto vivo, producto descontinuado, primera y última venta.

## Análisis ABC

**Qué es.** Una clasificación de productos por su aporte acumulado al valor de venta: A alto, B medio y C bajo.

**En el proyecto.** Se usó como contraste (ABC contrafactual): comparar qué productos capturaría un ABC puro por valor con los que captura la regla de priorización del negocio. La regla sí aporta algo que el ABC no ve: productos de bajo valor pero alta criticidad operativa, como el papel higiénico.

**Fuente.** Regla de priorización (cuaderno 02).

**También se dice.** ABC, Pareto, clasificación por valor, productos A.

## Regla de priorización

**Qué es.** Los criterios del negocio para marcar un producto como prioritario.

**En el proyecto.** Son 7 condiciones: espacio en bodega, perecedero, refrigerado, papel higiénico, temporada, top 50 por sucursal y frecuencia de venta. Las condiciones 6 y 7 no se usan como variables del modelo por fuga temporal, porque dependen de ordenar todo el histórico.

**Fuente.** Regla de priorización (cuaderno 02, notebooks/common_priorizacion.py).

**También se dice.** Productos prioritarios, condiciones 1 a 7, criticidad, productos críticos para el negocio.

## Efecto de calendario

**Qué es.** Cuánto cambia la venta esperada por un evento del calendario: un festivo, Semana Santa, la quincena o el bloque de diciembre.

**En el proyecto.** Se estima con una regresión conjunta (OLS) sobre todas las marcas de calendario a la vez, no una por una, para que el efecto de un evento no se confunda con el de otro cercano. La variable `factor_calendario_ventana` resume el efecto esperado en toda la ventana de 15 días del pronóstico, porque el modelo predice una demanda acumulada, no diaria.

**Fuente.** Calendario y estacionalidad (cuaderno 03); docs/INV-63-correccion-factor-calendario.md.

**También se dice.** Estacionalidad, festivos, quincena, Semana Santa, diciembre, temporada, factor de calendario.

## Intervalo de confianza

**Qué es.** El rango en el que probablemente está el valor real de una estimación.

**En el proyecto.** Si el intervalo de un efecto de calendario incluye 1,0 (sin efecto), el evento no se da por confirmado aunque el número puntual sugiera un efecto: así no se trata el ruido como señal. El conjunto de referencia del agente usa la misma idea para comparar modelos (diferencias pareadas con su intervalo).

**Fuente.** Calendario y estacionalidad (cuaderno 03) y docs/PLN-conjunto-referencia.md.

**También se dice.** IC, intervalo, margen de error, «cruza 1,0», significativo.

## Leave-one-year-out

**Qué es.** Una validación que entrena con todos los años menos uno y prueba en el que quedó fuera.

**En el proyecto.** Mide si un patrón estacional se repite de un año a otro, y no solo dentro del mismo año.

**Fuente.** Calendario y estacionalidad (cuaderno 03).

**También se dice.** LOYO, validación por año, dejar un año fuera.

## ADI y CV²

**Qué es.** Dos medidas del patrón de demanda de un producto en una sucursal. El ADI (intervalo promedio entre ventas) dice cada cuántos días se vende: un ADI alto es demanda poco frecuente. El CV² (coeficiente de variación al cuadrado) mide cuánto varía el tamaño de la venta cuando sí hay venta.

**En el proyecto.** Se cruzan para clasificar la demanda (clasificación de Syntetos-Boylan) y elegir la familia de modelo de cada producto.

**Fuente.** Patrón de demanda (cuadernos 04 y 07).

**También se dice.** ADI, CV2, frecuencia de venta, variabilidad, intervalo entre ventas.

## Patrón de demanda (Syntetos-Boylan)

**Qué es.** La clasificación de la demanda en 4 tipos según ADI y CV².

**En el proyecto.**
- **Suave:** frecuente y estable.
- **Errática:** frecuente, pero de tamaño variable.
- **Intermitente:** esporádica, pero de tamaño estable.
- **Lumpy:** esporádica y de tamaño variable; la más difícil de pronosticar.

Para elegir el modelo, la errática y la lumpy se agrupan con la intermitente. El pronóstico informa la rama de cada producto: intermitente, suave no perecedero o suave perecedero.

**Fuente.** Patrón de demanda (cuaderno 04 y 05) y servicio de modelos (rama del pronóstico).

**También se dice.** Demanda intermitente, demanda suave, errática, lumpy, rama del modelo, tipo de demanda.

## Racha de ceros

**Qué es.** La mayor cantidad de días hábiles seguidos sin venta de un producto en una sucursal.

**En el proyecto.** Junto con la frecuencia de venta, ayuda a decidir si un producto está realmente «vivo» o si su historia reciente es solo ruido.

**Fuente.** Patrón de demanda (cuaderno 04).

**También se dice.** Días sin venta, racha, tiempo sin vender.

## WAPE

**Qué es.** El error porcentual absoluto ponderado: la suma de los errores absolutos dividida por la suma de las ventas reales.

**En el proyecto.** Se usa en vez del MAPE porque no se rompe cuando la venta real es cero (frecuente en demanda intermitente) y pondera por volumen real.

**Fuente.** Baseline y métricas (cuaderno 04).

**También se dice.** WAPE, error del pronóstico, precisión, qué tan bueno es el pronóstico, MAPE.

## Línea base del pronóstico

**Qué es.** El desempeño de un método simple medido con el mismo protocolo que un modelo candidato, para que «superar la línea base» sea una comparación justa.

**En el proyecto.** La media móvil de 60 días fue el piso oficial, después de ganarle 4 de 4 pruebas al naive estacional (repetir el valor del mismo día de la semana del ciclo anterior).

**Fuente.** Baseline y métricas (cuadernos 04 y 05).

**También se dice.** Baseline, piso, media móvil, naive estacional, punto de comparación.

## Fuga temporal

**Qué es.** Cuando una variable del entrenamiento contiene información que, en producción, no estaría disponible al momento real del pronóstico.

**En el proyecto.** La forma más común: calcular una estadística (frecuencia, ranking) sobre todo el histórico en vez de solo sobre el pasado de cada fecha de pronóstico. Se evita con variables «as-of».

**Fuente.** Ingeniería de variables (cuaderno 07; docs/INV-15-feature-engineering.md).

**También se dice.** Fuga de datos, data leakage, mirar el futuro.

## Variable as-of

**Qué es.** Una variable recalculada usando solo los datos anteriores a una fecha de corte, en vez de una sola vez sobre todo el conjunto.

**En el proyecto.** Es la técnica central para evitar la fuga temporal en el pronóstico (matriz as-of del cuaderno 07).

**Fuente.** Ingeniería de variables (cuaderno 07; docs/INV-15-feature-engineering.md).

**También se dice.** As-of, feature as-of, fecha de corte, matriz as-of.

## Validación walk-forward

**Qué es.** Un protocolo donde cada prueba entrena con todo el pasado disponible hasta ese punto y prueba en el periodo siguiente, nunca al revés.

**En el proyecto.** Simula cómo se usa el modelo en producción. Es distinto de un corte al azar, que filtraría información del futuro, y de una validación cruzada estándar, que no respeta el orden del tiempo.

**Fuente.** Evaluación de modelos (cuadernos 09 a 14; docs/METODOLOGIA-EDA-MODELADO.md).

**También se dice.** Walk-forward, folds expansivos, validación temporal, backtesting.

## Origen del pronóstico

**Qué es.** La fecha desde la cual se predice hacia adelante.

**En el proyecto.** Los orígenes de entrenamiento se separan por el horizonte del pronóstico (15 días hábiles) para que las ventanas que se predicen no se solapen.

**Fuente.** Ingeniería de variables (cuaderno 07).

**También se dice.** Origen, fecha de corte, desde cuándo se pronostica.

## Cold start

**Qué es.** Un producto en una sucursal sin historia suficiente antes del origen para calcular sus variables de forma confiable.

**En el proyecto.** Se descarta explícitamente, informando cuánto se pierde; no se rellena con supuestos. Por eso hay productos sin pronóstico (Parte I).

**Fuente.** Ingeniería de variables (cuaderno 07).

**También se dice.** Producto nuevo, sin historia, arranque en frío.

## Demanda acumulada a 15 días

**Qué es.** Lo que predice el modelo: la suma de unidades vendidas en los 15 días hábiles siguientes al origen, no la venta de un solo día.

**En el proyecto.** Es la variable objetivo `target_demanda_15d`. Por eso el pronóstico tiene un solo horizonte.

**Fuente.** Modelado (cuadernos 07c a 13; docs/INV-17-modelo-baseline.md).

**También se dice.** Target, variable objetivo, demanda a 15 días, horizonte.

## LightGBM

**Qué es.** Un método de *gradient boosting* sobre árboles de decisión: cada árbol nuevo corrige los errores de los anteriores.

**En el proyecto.** Es flexible, pero necesita bastantes datos para no sobreajustarse. Con regresión cuantílica predice cuantiles de la demanda. Es el modelo del pronóstico en la rama intermitente (el 71,1 % del conjunto): LightGBM cuantílico con 434 árboles y 78 hojas, afinado con búsqueda bayesiana. Las ramas suaves usan un ensamble de Tweedie y LightGBM (ver «Ensamble y modelo hurdle»).

**Fuente.** Familias de modelo (cuadernos 08 a 15; docs/INV-17-modelo-baseline.md).

**También se dice.** LightGBM, árboles, boosting, modelo de IA, modelo de machine learning, qué modelo usa el pronóstico, modelo del pronóstico.

## Regresión cuantílica

**Qué es.** Una regresión que, en vez de predecir la media, predice un cuantil de la distribución: por ejemplo la mediana (0,5) o el cuantil 0,89.

**En el proyecto.** LightGBM la usa cambiando su función de pérdida (la pinball loss). Así se obtienen la venta esperada (mediana) y la cobertura recomendada (cuantil de negocio).

**Fuente.** Familias de modelo y calibración (cuadernos 13 y 14).

**También se dice.** Cuantil, mediana, percentil, regresión por cuantiles.

## GLM y regresión Tweedie

**Qué es.** Un modelo lineal generalizado (GLM) es una regresión lineal cuya variable objetivo puede seguir otra distribución (Poisson, Tweedie). La Tweedie interpola entre la normal, la Poisson y la gamma según su parámetro `power`.

**En el proyecto.** Es mucho más simple que un ensamble de árboles, y con poca muestra esa simplicidad generaliza mejor. El `power = 0` ganador equivale en la práctica a una regresión Ridge (lineal regularizada) sobre la demanda, no a un modelo de conteo.

**Fuente.** Familias de modelo (cuadernos 08 y 11; docs/INV-17-modelo-baseline.md).

**También se dice.** GLM, Tweedie, Ridge, regresión lineal, Poisson.

## Regularización y sobreajuste

**Qué es.** El sobreajuste es cuando un modelo aprende el ruido de los datos de entrenamiento y no generaliza: se ve muy bien en entrenamiento y mal en datos nuevos. La regularización penaliza el tamaño de los coeficientes o las hojas para evitarlo: más regularización, modelo más simple.

**En el proyecto.** El sobreajuste se diagnosticó en las ramas suaves con los hiperparámetros por defecto de LightGBM.

**Fuente.** Familias de modelo (cuaderno 08).

**También se dice.** Overfitting, sobreajuste, regularización, alpha, L1, L2.

## Croston y SBA

**Qué es.** Un método clásico para demanda intermitente: estima por separado el tamaño de la venta cuando ocurre y el intervalo entre ventas. SBA corrige un sesgo conocido del método original con el factor 1 − alpha/2.

**En el proyecto.** Se probó en la rama intermitente y perdió contra la media móvil: es un hallazgo negativo documentado, no se usa.

**Fuente.** Familias de modelo (cuadernos 04 y 08).

**También se dice.** Croston, SBA, Syntetos-Boylan Approximation, método para intermitentes.

## Ensamble y modelo hurdle

**Qué es.** Un ensamble combina las predicciones de dos o más modelos, por ejemplo con un promedio ponderado, para reducir el error cuando los modelos no se equivocan en los mismos casos. Un modelo hurdle tiene dos partes: un clasificador estima si habrá venta y otro modelo, entrenado solo con las ventas positivas, estima cuánto.

**En el proyecto.** Las ramas suaves del pronóstico usan un ensamble de Tweedie y LightGBM, con un peso de Tweedie de 0,5 en suave no perecedero y de 0,6 en suave perecedero. El hurdle se probó y se descartó en la rama suave perecedero, porque la premisa (que hubiera ceros en la demanda) resultó falsa para esa rama.

**Fuente.** Familias de modelo (cuaderno 08; docs/INV-17-modelo-baseline.md).

**También se dice.** Ensamble, blend, combinación de modelos, hurdle, modelo de dos partes.

## Reconciliación jerárquica

**Qué es.** Una técnica que comparte información entre series relacionadas (por ejemplo, productos de la misma categoría) en vez de ajustar cada una por separado.

**En el proyecto.** Reduce la variación en series con poca historia «tomando prestada» señal de las que tienen más. Se propuso como siguiente paso para las ramas suaves; no está implementada.

**Fuente.** Síntesis y modelado (cuaderno 05; docs/INV-17-modelo-baseline.md).

**También se dice.** Pooling parcial, jerarquía, reconciliación, compartir información entre productos.

## Cuantil de negocio

**Qué es.** El nivel de cuantil del pronóstico que refleja la aversión al riesgo del negocio.

**En el proyecto.** Es 0,89 en los no perecederos (mejor sobrar que faltar) y 0,17 en los perecederos (el sobrante pesa más que el faltante). Sale de la fórmula del cuantil óptimo con costos asimétricos: Cu ÷ (Cu + Co), donde Cu es el costo de quedarse corto (quiebre) y Co el de pasarse (sobrante o merma), el problema del «vendedor de periódicos». En la aplicación es la cobertura recomendada (Parte I).

**Fuente.** Cuantiles y costos (cuaderno 13).

**También se dice.** Cuantil de negocio, alpha de negocio, newsvendor, costo de quiebre, costo de sobrante.

## Calibración y cobertura empírica

**Qué es.** La cobertura empírica es la fracción real de casos en que la venta quedó por debajo del cuantil pronosticado; si se pidió el 0,89, debería acercarse a 0,89. La calibración es qué tanto coinciden.

**En el proyecto.** Un modelo puede tener buen WAPE y aun así estar mal calibrado en sus cuantiles: son propiedades distintas. No es lo mismo que los días de cobertura del inventario (Parte I).

**Fuente.** Cuantiles y calibración (cuadernos 08, 13 y 14).

**También se dice.** Calibración, cobertura empírica, qué tan confiable es el rango, mal calibrado.

## Recalibración conformal

**Qué es.** Un método posterior al modelo, que no depende de él, para corregir la calibración de un cuantil (Split-CQR). Se aparta una parte de los datos que el modelo nunca vio, se mide cuánto se equivoca ahí, y ese error se usa para desplazar la predicción en datos nuevos.

**En el proyecto.** No supone nada sobre la forma del error; por eso funcionó donde otros intentos fallaron.

**Fuente.** Calibración (cuaderno 14; docs/INV-17-modelo-baseline.md, offset conformal).

**También se dice.** Conformal, Split-CQR, recalibración, offset conformal.

## Pinball loss

**Qué es.** La función de pérdida de la regresión cuantílica: penaliza distinto un error por exceso que uno por defecto, según el cuantil.

**En el proyecto.** Es la métrica que sí tiene en cuenta el cuantil; el MAE o el WAPE asumen la mediana.

**Fuente.** Calibración y cuantiles (cuadernos 13 y 14).

**También se dice.** Pinball, pérdida cuantílica, quantile loss.

## Sesgo de selección en la evaluación

**Qué es.** El riesgo de que una mejora medida venga en parte de haber probado muchas configuraciones y quedarse con la que mejor salió en ese conjunto de prueba, sin que se sostenga en datos nuevos.

**En el proyecto.** Por eso se valida con particiones excluidas y semillas alternativas, y se documenta cuándo una mejora depende de una sola partición (docs/INV-62-inventario-real.md §4). En el agente, por la misma razón, el conjunto v1 es un examen que no se usa para ajustar.

**Fuente.** Validación (docs/INV-62-inventario-real.md) y docs/PLN-conjunto-referencia.md.

**También se dice.** Sesgo de selección, sobreajuste a la prueba, selection bias, buenas prácticas.

## Huella

**Qué es.** Un resumen SHA-256 de un archivo o de un conjunto de datos que cambia si cambia cualquier parte.

**En el proyecto.** Cada cuaderno guarda la huella de sus entradas y salidas, y el siguiente la verifica antes de leer. El arnés del agente guarda la huella del conjunto, el catálogo y el prompt de cada corrida.

**Fuente.** Cadena de cuadernos (huella_0N.json) y arnés del agente (nlp_agent/evaluacion/correr.py).

**También se dice.** Huella, hash, fingerprint, SHA-256, verificación.

## MLflow

**Qué es.** Un sistema de registro de experimentos: un experimento agrupa runs (corridas), cada una con sus parámetros, métricas y archivos, para consultarlos sin volver a correr nada.

**En el proyecto.** En el modelado, cada ronda de búsqueda de modelos tiene su experimento. En el agente, cada conjunto de referencia (v0 y v1) es un experimento en el MLflow local, con sus prompts, datasets y versiones del agente.

**Fuente.** Modelado (docs/INV-17-modelo-baseline.md) y docs/NLP-AGENT.md (trazabilidad en MLflow).

**También se dice.** MLflow, experimento, run, corrida, registro de experimentos.

## Optuna y TPE

**Qué es.** Una librería y un algoritmo de búsqueda bayesiana de hiperparámetros: usan los resultados de los intentos anteriores para decidir qué probar después.

**En el proyecto.** Es más eficiente que probar combinaciones al azar o todas, con el mismo presupuesto de intentos.

**Fuente.** Búsqueda de hiperparámetros (cuadernos 08 y 15).

**También se dice.** Optuna, TPE, búsqueda de hiperparámetros, ajuste del modelo.
