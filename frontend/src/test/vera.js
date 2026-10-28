/**
 * InventAI/o — Flujos de Vera para las pruebas (INV-35)
 * Tomados de respuestas reales del agente por Nginx el 24-oct (contrato v1.1).
 */

export const META = ['meta', { request_id: 'r-1', modelo: 'qwen3:8b', version_prompt: 'v2' }]

const DATOS_GLORIETA = {
  id: '1-1',
  herramienta: 'resumen_alertas',
  forma: 'tabla',
  titulo: 'Resumen de alertas · GLORIETA',
  columnas: [
    { clave: 'sucursal', titulo: 'Sucursal', tipo: 'texto' },
    { clave: 'critica', titulo: 'Crítica', tipo: 'numero' },
    { clave: 'media', titulo: 'Media', tipo: 'numero' },
  ],
  filas: [{ sucursal: 'GLORIETA', critica: '243', media: '1.092' }],
  total: 1,
  mostrando: 1,
  fecha_dato: '2025-12-31',
}

export const DONE = {
  tokens_prompt: 3086, tokens_respuesta: 43, ms_total: 2988, ms_modelo: 1377, ms_herramientas: 1590,
  rondas: 2, fechas_datos: ['2025-12-31'], fidelidad: 'ok', respaldo: false,
  sugerencias: ['¿Quieres ver las alertas críticas?'], turnos_recortados: 0,
}

// Gerente: «¿Cuántas alertas críticas hay en GLORIETA?»
export const FLUJO_ALERTAS = [
  META,
  ['tool', { id: '1-1', nombre: 'resumen_alertas', estado: 'inicio', etiqueta: 'Resumen de alertas · GLORIETA', lenta: false }],
  ': ping',
  ['tool', { id: '1-1', nombre: 'resumen_alertas', estado: 'ok', ms: 1590, codigo: null }],
  ['data', DATOS_GLORIETA],
  ['token', { texto: 'En GLORIETA hay ' }],
  ['token', { texto: '**243** alertas críticas.' }],
  ['done', DONE],
]

// admin_sucursal de LA 21 preguntando por GLORIETA: el 403 llega dentro del flujo
export const FLUJO_403 = [
  META,
  ['tool', { id: '1-1', nombre: 'resumen_inventario', estado: 'inicio', etiqueta: 'Resumen del inventario · GLORIETA', lenta: false }],
  ['tool', { id: '1-1', nombre: 'resumen_inventario', estado: 'error', ms: 300, codigo: 403 }],
  ['token', { texto: 'No tienes permiso para consultar esa información.' }],
  ['done', { ...DONE, fechas_datos: [], sugerencias: [] }],
]
