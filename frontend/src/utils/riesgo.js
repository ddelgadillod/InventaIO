/**
 * InventAI/o — Riesgo según el pronóstico (INV-26, V5)
 * Días hábiles hasta agotarse = stock / (q50 / 15), con los umbrales de las
 * políticas de INV-21 (politicas_inv21.json: urgente ≤ 5, alta ≤ 10). Es la
 * lectura del stock de la foto: no suma los traslados en camino, como sí hace
 * INV-21. La otra lectura, la cobertura del semáforo, sale del ETL.
 *
 * Los días se redondean a un decimal antes de compararlos, para que el valor
 * y la etiqueta coincidan en pantalla: 5,03 se ve "5,0" y es urgente, no alta
 * (HUEVOS *UND en LA 21). toFixed redondea como fmtDecimal.
 */

export const HORIZONTE_DIAS_HABILES = 15
export const UMBRALES_RIESGO = { urgente: 5, alta: 10 }

// → { nivel, dias }: nivel es una clave de RIESGOS_PRONOSTICO (etiquetas.js);
// dias es null cuando no hay demanda prevista o el stock es negativo
export function calcularRiesgo(stock, q50, horizonte = HORIZONTE_DIAS_HABILES) {
  if (stock < 0) return { nivel: 'inconsistencia', dias: null }
  if (!(q50 > 0)) return { nivel: 'sin_demanda', dias: null }
  const dias = Number((stock / (q50 / horizonte)).toFixed(1))
  if (dias <= UMBRALES_RIESGO.urgente) return { nivel: 'urgente', dias }
  if (dias <= UMBRALES_RIESGO.alta) return { nivel: 'alta', dias }
  return { nivel: 'normal', dias }
}
