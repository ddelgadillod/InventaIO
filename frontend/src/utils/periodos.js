/**
 * InventAI/o — Períodos de la vista de reportes (INV-26 fix, K7)
 * Los atajos se calculan desde el rango de datos que entrega la API
 * (datos_desde y datos_hasta de /reportes/ventas), no desde fechas fijas.
 */

export const ATAJOS = { mes: 'Mes', trimestre: 'Trimestre', anio: 'Año', todo: 'Todo' }

// La agrupación con que abre cada atajo; el rango libre abre por día
export const AGRUPACION_DEL_ATAJO = { mes: 'dia', trimestre: 'semana', anio: 'mes', todo: 'mes', rango: 'dia' }

// El mes, el trimestre o el año de la última venta, o toda la historia
export function rangoDelAtajo(atajo, { desde, hasta }) {
  if (atajo === 'todo') return { desde, hasta }
  const [anio, mes] = hasta.split('-').map(Number)
  const primerMes = { mes, trimestre: Math.floor((mes - 1) / 3) * 3 + 1, anio: 1 }[atajo]
  const inicio = `${anio}-${String(primerMes).padStart(2, '0')}-01`
  return { desde: inicio < desde ? desde : inicio, hasta }
}
