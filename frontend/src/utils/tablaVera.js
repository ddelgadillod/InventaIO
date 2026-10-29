/**
 * InventAI/o — Tablas de Vera a CSV (M4 de INV-35)
 * Las celdas llegan del agente como texto en es-CO ("1.092", "5 unidades", "$ 151.640").
 * Para que Excel las tome como números se convierten las columnas `numero`, las
 * `cantidad` de una sola unidad (la unidad pasa al título) y los montos («$ …», que
 * llegan como `texto`). Lo demás va como texto; el formato del archivo es el de csv.js.
 */
import { aCSV } from './csv'

const NUMERO = /^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$/
const CANTIDAD = /^(\S+) (unidad|unidades|kg)$/
const MONTO = /^\$ ?(\S+)$/

// "1.092" → 1092, "-27,6" → -27.6; si no es un número en es-CO, null
export function numeroEsCO(texto) {
  if (typeof texto !== 'string' || !NUMERO.test(texto.trim())) return null
  return Number(texto.trim().replace(/\./g, '').replace(',', '.'))
}

const vacia = v => v === undefined || v === null || v === ''

// Cómo sale cada columna en el CSV: { titulo, valor: fila => número o texto }
function columnaCSV({ clave, titulo, tipo }, filas) {
  const valores = filas.map(f => f[clave]).filter(v => !vacia(v))
  const como = (patron, grupo = 1) => fila => {
    const m = patron.exec(fila[clave] ?? '')
    return m ? numeroEsCO(m[grupo]) : null
  }
  if (tipo === 'numero' && valores.every(v => numeroEsCO(v) !== null)) {
    return { titulo, valor: f => (vacia(f[clave]) ? null : numeroEsCO(f[clave])) }
  }
  if (tipo === 'cantidad') {
    const partes = valores.map(v => CANTIDAD.exec(v))
    const unidades = new Set(partes.map(p => (p?.[2] === 'kg' ? 'kg' : 'unidades')))
    if (valores.length && partes.every(p => p && numeroEsCO(p[1]) !== null) && unidades.size === 1) {
      return { titulo: `${titulo} (${[...unidades][0]})`, valor: como(CANTIDAD) }
    }
  }
  if (valores.length && valores.every(v => numeroEsCO(MONTO.exec(v)?.[1]) !== null)) {
    return { titulo: `${titulo} ($)`, valor: como(MONTO) }
  }
  return { titulo, valor: f => (vacia(f[clave]) ? null : f[clave]) }
}

/** El texto CSV de un evento `data` de Vera. */
export function tablaACSV({ columnas = [], filas = [] }) {
  return aCSV(columnas.map(c => columnaCSV(c, filas)), filas)
}

/** "Resumen de alertas · GLORIETA" → "vera-resumen-de-alertas-glorieta.csv" */
export function nombreCSV(titulo) {
  const base = (titulo || 'datos').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return `vera-${base || 'datos'}.csv`
}
