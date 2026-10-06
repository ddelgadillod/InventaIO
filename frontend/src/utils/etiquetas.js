/**
 * InventAI/o — Etiquetas y reglas de presentación (INV-26 fix, A2.11)
 * Una sola fuente para los nombres que muestran las páginas: tipos y
 * urgencias de alerta (INV-25, D4), estados de inventario (H3), ubicaciones y
 * los valores del pronóstico y de las recomendaciones (INV-26 e INV-27, V7).
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

// Un valor nuevo de la API sin etiqueta se ve legible ("tipo futuro") en vez de romper la página
export function etiquetaDe(etiquetas, valor) {
  if (valor === null || valor === undefined) return '—'
  return etiquetas[valor] ?? String(valor).replace(/_/g, ' ')
}

export function etiquetaTipoAlerta(tipo) {
  return etiquetaDe(TIPOS_ALERTA, tipo)
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

// ── Pronóstico y recomendaciones (INV-26 e INV-27) ──
// Urgencia de las recomendaciones de INV-21 e INV-22 (vigilancia solo en
// transferencias); el riesgo según el pronóstico usa las mismas tres primeras
export const URGENCIAS_RECOMENDACION = {
  urgente: 'Urgente',
  alta: 'Alta',
  normal: 'Normal',
  vigilancia: 'Vigilancia',
}

// Riesgo según el pronóstico (V5): las urgencias y dos casos sin días hasta agotarse
export const RIESGOS_PRONOSTICO = {
  urgente: URGENCIAS_RECOMENDACION.urgente,
  alta: URGENCIAS_RECOMENDACION.alta,
  normal: URGENCIAS_RECOMENDACION.normal,
  sin_demanda: 'Sin demanda prevista',
  inconsistencia: TIPOS_ALERTA.inconsistencia_inventario,
}

// Rama del modelo de INV-20 con la que se pronosticó el par; los mismos
// nombres que la interpretación de ml_service
export const RAMAS_MODELO = {
  intermitente: 'Demanda intermitente',
  suave_no_perecedero: 'Demanda estable',
  suave_perecedero: 'Demanda estable, producto perecedero',
}
