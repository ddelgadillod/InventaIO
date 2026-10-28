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
