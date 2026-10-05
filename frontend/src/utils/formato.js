/**
 * InventAI/o — Formato de números y fechas (INV-26 fix, A2.11)
 * Una sola implementación para todas las páginas: separador de miles y
 * decimales de es-CO; fechas ISO de la API sin pasar por la zona horaria.
 */

const ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 })
const UN_DECIMAL = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

// 4608 → "4.608"
export function fmtNumero(n) {
  return n === null || n === undefined ? '—' : ENTERO.format(n)
}

// 5.3 → "5,3"
export function fmtDecimal(n) {
  return n === null || n === undefined ? '—' : UN_DECIMAL.format(n)
}

// Cantidad de stock o de ventas según la `unidad` del producto: un decimal en
// los que se venden por kilo ("77,1"), enteros en los demás ("556")
export function fmtCantidad(n, unidad) {
  return unidad === 'kg' ? fmtDecimal(n) : fmtNumero(n)
}

// Moneda corta, la misma que usaba el Dashboard de Release 1: $737.9M, $57K, $850
export function fmtMonedaCorta(n) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

// "2025-12-31" → "31 dic 2025"
export function fmtFecha(iso) {
  if (!iso) return '—'
  const [anio, mes, dia] = iso.slice(0, 10).split('-')
  return `${Number(dia)} ${MESES[Number(mes) - 1]} ${anio}`
}

// Período de los reportes según la agrupación: "2025-12-31" → "31 dic",
// "2025-W49" → "Sem 49 2025", "2025-12" → "dic 2025"
export function fmtPeriodo(periodo) {
  const semana = /^(\d{4})-W(\d{2})$/.exec(periodo)
  if (semana) return `Sem ${Number(semana[2])} ${semana[1]}`
  const mes = /^(\d{4})-(\d{2})$/.exec(periodo)
  if (mes) return `${MESES[Number(mes[2]) - 1]} ${mes[1]}`
  return fmtFecha(periodo).replace(/ \d{4}$/, '')
}
