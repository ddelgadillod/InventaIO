import { fmtDecimal, fmtNumero, fmtPeriodo } from './formato'

/**
 * INV-40 (contrato v1.2 del evento `data`): utilidades de las tarjetas y la gráfica de Vera.
 */

// ¿La consulta trae algo visual? Una gráfica sin datos no cuenta
export function tieneVisual(datos) {
  return Boolean(datos.tarjetas?.length || datos.grafico?.datos?.length)
}

const COLOR_SERIE = {
  ok: '#059669', bajo: '#D97706', critico: '#DC2626', inconsistencia: '#7C3AED',
  critica: '#DC2626', alta: '#D97706', media: '#64748B',
  valor: '#2563EB', margen: '#14B8A6', stock: '#059669', demanda: '#2563EB',
}
const PALETA = ['#2563EB', '#14B8A6', '#D97706', '#7C3AED', '#DC2626', '#64748B']
const COMPACTO = new Intl.NumberFormat('es-CO', { notation: 'compact', maximumFractionDigits: 1 })
const PERIODO = /^\d{4}-(\d{2}(-\d{2})?|W\d{2})$/

export function colorSerie(clave, i) {
  return COLOR_SERIE[clave] ?? PALETA[i % PALETA.length]
}

export function valorCorto(valor, unidad) {
  if (valor === null || valor === undefined) return '—'
  return unidad === '$' ? `$ ${COMPACTO.format(valor)}` : COMPACTO.format(valor)
}

export function valorLargo(valor, unidad) {
  if (valor === null || valor === undefined) return '—'
  if (unidad === '$') return `$ ${fmtNumero(valor)}`
  return `${unidad === 'kg' ? fmtDecimal(valor, 1) : fmtNumero(valor)} ${unidad || ''}`.trim()
}

export function etiquetaEje(valor) {
  const texto = String(valor ?? '')
  if (PERIODO.test(texto)) return fmtPeriodo(texto)
  return texto.length > 22 ? `${texto.slice(0, 21)}…` : texto
}

