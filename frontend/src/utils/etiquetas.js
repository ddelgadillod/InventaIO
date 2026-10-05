/**
 * InventAI/o — Etiquetas y reglas de presentación (INV-26 fix, A2.11)
 * Una sola fuente para los nombres que muestran las páginas: tipos y
 * urgencias de alerta (INV-25, D4), estados de inventario (H3) y ubicaciones.
 */
import { fmtDecimal } from './formato'

export const TIPOS_ALERTA = {
  inconsistencia_inventario: 'Inconsistencia de inventario',
  stock_critico: 'Stock crítico',
  stock_bajo: 'Stock bajo',
  sin_movimiento: 'Sin movimiento',
  rotacion_baja: 'Rotación baja',
}

export const URGENCIAS = { critica: 'Crítica', alta: 'Alta', media: 'Media' }

// Agrupación de los reportes de ventas (dia, semana, mes en la API)
export const AGRUPACIONES = { dia: 'Día', semana: 'Semana', mes: 'Mes' }

export function etiquetaTipoAlerta(tipo) {
  return TIPOS_ALERTA[tipo] ?? tipo.replace(/_/g, ' ')
}

export const BODEGA = 'bodega_central'

// La Bodega se muestra con un nombre legible; las sucursales, con el suyo
export function nombreUbicacion({ nombre, tipo }) {
  return tipo === BODEGA ? 'Bodega Central' : nombre
}

// Las series de ventas por sucursal traen solo el nombre. SIN_SUCURSAL son las
// ventas sin terminal asignada (hasta 2025-09-06, INV-25): suman al total
export function nombreSerieVentas(sucursal) {
  if (sucursal == null) return 'Total'
  return sucursal === 'SIN_SUCURSAL' ? 'Sin sucursal' : sucursal
}

// `unidad` de los productos del Core API: en qué se cuentan el stock y las
// ventas ('kg' si se vende por kilo). No confundir con unidad_medida, que es
// la de la presentación (g, ml)
export function textoUnidadVenta(unidad) {
  return unidad === 'kg' ? 'Se vende por kilo (kg)' : 'Se vende por unidad'
}

// ── Inventario ─────────────────────────────────────
// dias_cobertura vale exactamente 999 cuando la demanda observada es 0
// (centinela del ETL, construir_fact_inventario_real.py). Una cobertura
// mayor que 999 es real: el producto vende, pero muy poco
export const COBERTURA_SIN_VENTAS = 999

// Los estados del semáforo de la API; "inconsistencia" es el stock negativo (K3)
export const ESTADOS_INVENTARIO = {
  ok: '✓ OK',
  bajo: '⚠ Bajo',
  critico: '✕ Crítico',
  inconsistencia: '◆ Inconsistencia',
}

export function textoCobertura(dias, stock) {
  if (stock < 0) return '—'
  if (dias === COBERTURA_SIN_VENTAS) return 'Sin ventas'
  return `${fmtDecimal(dias)} d`
}
