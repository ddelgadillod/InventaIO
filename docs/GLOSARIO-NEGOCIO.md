# Glosario de negocio

Términos y reglas de InventAI/o en lenguaje sencillo, para quienes usan la aplicación y para el asistente (INV-31). Cada término dice qué es, la regla que aplica el sistema, un ejemplo con la foto de inventario del 31 de diciembre de 2025 y de dónde sale.

El agente consulta este documento con la herramienta `buscar_en_glosario`. Cada sección `##` es un fragmento: su título es el término y la línea «También se dice» trae las palabras con que la gente lo pregunta. Las cifras de las reglas se comprueban contra el código en las pruebas, para que no se desactualicen. `nlp_agent/conocimiento/corpus.json` se genera desde aquí con `python -m conocimiento.construir`.

Los términos técnicos del pronóstico (features, modelos, métricas) están en `docs/GLOSARIO.md`.

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

**Ejemplo.** Si en los días que cubre el pedido se espera vender 100 unidades y entre el stock y lo que viene hay 60, se compra. Si el límite alto del pronóstico es 130, se piden 70.

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

**Ejemplo.** Una leche que requiere frío se pide el martes directo para GLORIETA; un arroz se pide el 2 o el 16 y llega a la sucursal desde la bodega.

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

**Ejemplo.** ARROZ DIANA *500 GR en PRINCIPAL: 677 unidades en 15 días hábiles, con una cobertura recomendada de hasta 1.068.

**Fuente.** Servicio de modelos y Core API (`POST /api/ml/predict`, INV-20 e INV-25).

**También se dice.** Pronóstico, predicción, cuánto voy a vender, demanda esperada, proyección.

## Días hábiles

**Qué es.** Los días en que hay operación. Todas las cuentas de pronóstico, compras y traslados se hacen en días hábiles.

**Regla.** Hacia atrás, son los días con alguna venta en la red. Hacia adelante, los del calendario sin cierres programados. 15 días hábiles son unas tres semanas.

**Ejemplo.** El historial de ventas muestra las ventas en periodos de 15 días hábiles, y el pronóstico mira los 15 días hábiles siguientes a la foto.

**Fuente.** Políticas de compras y traslados, INV-21 e INV-22.

**También se dice.** Días hábiles, días de operación, horizonte, 15 días.

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

**Ejemplo.** Si GLORIETA tiene más de su máximo de un producto y LA 21 está en rojo, se sugiere trasladar la diferencia de GLORIETA a LA 21.

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
