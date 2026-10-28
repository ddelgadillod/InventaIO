/**
 * InventAI/o — Preguntas rápidas de Vera por rol (INV-35, CA 7)
 * Salen del conjunto de referencia v1 (nlp_agent/evaluacion/conjuntos/v1), pero
 * con la ortografía corregida y sin nombres de sucursal propios del usuario:
 * cada una tiene que servir sola, con los permisos del rol que la hace.
 * Validadas el 27-oct contra el agente real con un usuario de cada rol (M1): «Dame
 * un reporte general de las alertas por nivel» terminaba en respuesta de respaldo
 * con el gerente y se cambió por el ranking, que pasó 4 de 4.
 * Las de seguimiento llegan en `done.sugerencias` y no se listan aquí.
 */
export const PREGUNTAS_RAPIDAS = {
  gerente: [
    'Dame un ranking de alertas por sucursal',
    'Dame el estado de alertas de Glorieta',
    '¿Qué recomendaciones de traslado hay hacia Principal?',
    'Dame un reporte de ventas de los últimos 90 días',
  ],
  admin_bodega: [
    'Dame el estado general de sucursales',
    'Dame un reporte de las alertas generadas por IA',
    'Sugiéreme los productos que debo comprar con urgencia',
    '¿Qué significa el punto de pedido?',
  ],
  admin_sucursal: [
    'Dame un reporte general de inventario',
    '¿Cómo estamos de alertas?',
    'Dame el sugerido de pedidos a proveedor',
    '¿Qué significa el color rojo en el semáforo?',
  ],
}

export const preguntasRapidasDelRol = rol => PREGUNTAS_RAPIDAS[rol] ?? []

/**
 * M12: en las páginas de datos, las preguntas rápidas son de esa página. `red` son las de
 * quien ve todas las ubicaciones (gerente y admin_bodega); `sucursal`, las del
 * admin_sucursal, que se refieren a la suya sin nombrarla. Validadas el 27-oct contra el
 * agente con dos usuarios de cada grupo (60 casos, y 18 más para los reemplazos):
 * - las de «estado general» de toda la red caían en respaldo con el gerente (varias
 *   consultas a la vez) y se cambiaron por una sucursal;
 * - «los productos más vendidos» no tiene herramienta que ordene por producto (el
 *   agente devolvía totales por periodo) y se cambió por las ventas de un producto;
 * - «ventas de diciembre» daba 422 (el filtro de un mes, C1, está apagado) y se cambió
 *   por las ventas por año.
 * En el Dashboard y en una página sin lista, las del rol.
 */
export const PREGUNTAS_POR_PAGINA = {
  '/alertas': {
    titulo: 'Alertas',
    red: ['¿Cuántas alertas críticas hay en GLORIETA?', 'Dame un ranking de alertas por sucursal', 'Dame un reporte de las alertas generadas por IA'],
    sucursal: ['¿Cómo estamos de alertas?', 'Dame un reporte general de las alertas por nivel', '¿Qué alertas generadas por IA tenemos?'],
  },
  '/inventario': {
    titulo: 'Inventario',
    red: ['Dame el estado del inventario de LA 21 en forma de semáforo', '¿Cuántos productos hay en estado crítico en GLORIETA?', '¿Qué productos están en estado crítico en PRINCIPAL?'],
    sucursal: ['Dame un reporte general de inventario', '¿Qué productos están en estado crítico?', '¿Qué significa el color rojo en el semáforo?'],
  },
  '/recomendaciones': {
    titulo: 'Recomendaciones',
    red: ['Sugiéreme los productos que debo comprar con urgencia', '¿Qué traslados prioritarios hay?', '¿Cuál es el calendario de pedidos?'],
    sucursal: ['Dame el sugerido de pedidos a proveedor', '¿Qué traslados urgentes llegan a mi sucursal?', '¿Qué significa el punto de pedido?'],
  },
  '/predicciones': {
    titulo: 'Predicciones',
    red: ['¿Cuál es el pronóstico de HUEVOS *UND en LA 21?', '¿Alcanza el stock de HUEVOS *UND en GLORIETA para los próximos 15 días hábiles?', '¿Qué es la cobertura?'],
    sucursal: ['¿Cuál es el pronóstico de HUEVOS *UND?', '¿Alcanza el stock de HUEVOS *UND para los próximos 15 días hábiles?', '¿Qué es la cobertura?'],
  },
  '/reportes': {
    titulo: 'Reportes',
    red: ['Dame un reporte de ventas de los últimos 90 días', 'Dame las ventas por sucursal del último mes', '¿Cuánto se ha vendido de HUEVOS *UND en los últimos 90 días?'],
    sucursal: ['Dame las ventas de los últimos 30 días', 'Dame las ventas por año', '¿Cuánto se ha vendido de HUEVOS *UND en los últimos 30 días?'],
  },
}

/** { titulo, preguntas }: las de la página si las hay (titulo = su nombre), si no, las del rol (titulo null). */
export function preguntasRapidas(rol, ruta) {
  const pagina = PREGUNTAS_POR_PAGINA[ruta]
  if (pagina && rol in PREGUNTAS_RAPIDAS) {
    return { titulo: pagina.titulo, preguntas: pagina[rol === 'admin_sucursal' ? 'sucursal' : 'red'] }
  }
  return { titulo: null, preguntas: preguntasRapidasDelRol(rol) }
}

/**
 * «Preguntar a Vera» desde una alerta (M7). Validadas el 27-oct con el gerente, los
 * administradores de sucursal y la Bodega: usan el inventario y el pronóstico, que
 * responden bien producto por producto. Las de traslados y compras no se ofrecen: el
 * agente asumía la dirección del traslado según el rol y las compras no se filtran
 * por producto (H13 de docs/INV-35-chat.md).
 */
export function preguntaDeAlerta(alerta) {
  const producto = alerta.nombre_producto ?? alerta.codigo_item
  const sucursal = alerta.sucursal
  if (alerta.tipo === 'riesgo_desabastecimiento_ml') {
    return `¿Alcanza el stock de ${producto} en ${sucursal} para los próximos 15 días hábiles?`
  }
  if (alerta.tipo === 'sobrestock_previsto_ml') return `¿Cuál es el pronóstico de ${producto} en ${sucursal}?`
  return `¿Cómo está el inventario de ${producto} en ${sucursal}?`
}
