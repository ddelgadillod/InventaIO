import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Dashboard from './Dashboard'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

const KPIS = {
  // En riesgo = bajo + crítico del semáforo (K9)
  ventas_hoy: 56756777.23, ventas_mes: 737879055.35, productos_en_riesgo: 1500, stock_valorizado: 958834997.785,
  fecha_referencia: '2025-12-31', variacion_ventas_hoy_pct: -1.4, variacion_ventas_mes_pct: 54.3,
}
const KPIS_BODEGA = {
  ventas_hoy: 0, ventas_mes: 0, productos_en_riesgo: 671, stock_valorizado: 355986371.7,
  fecha_referencia: '2025-12-31', variacion_ventas_hoy_pct: null, variacion_ventas_mes_pct: null,
}
const RESUMEN_ALERTAS = {
  items: [], global_: { critica: 1334, alta: 386, media: 2732, total: 4452 },
  por_tipo: { inconsistencia_inventario: 220, stock_critico: 1114, stock_bajo: 386, sin_movimiento: 2453, rotacion_baja: 279 },
}
const TENDENCIA = {
  series: [{ sucursal: null, puntos: [
    { fecha: '2025-12-30', valor_total: 30000000, cantidad: 1, promedio_movil_7d: 25000000 },
    { fecha: '2025-12-31', valor_total: 56756777.23, cantidad: 1, promedio_movil_7d: null },
  ] }],
  fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31',
}

function rutas(cambios = {}) {
  return {
    'GET /api/reportes/kpis': ({ params }) => ({ body: params.sucursal_id === '5' ? KPIS_BODEGA : KPIS }),
    'GET /api/consulta/inventario/resumen': {
      body: { items: [], global_: { ok: 3611, bajo: 138, critico: 202, inconsistencia: 95, total: 4046 }, fecha_inventario: '2025-12-31' },
    },
    'GET /api/alertas/resumen': { body: RESUMEN_ALERTAS },
    'GET /api/reportes/tendencias': { body: TENDENCIA },
    'GET /api/reportes/ventas/top-productos': {
      body: { items: [{ nombre: 'HUEVOS *UND', valor_total: 5000000 }, { nombre: 'UN NOMBRE DE PRODUCTO MUY LARGO *KG', valor_total: 900 }] },
    },
    ...cambios,
  }
}

describe('Dashboard (A3.2)', () => {
  it('rotula las ventas con la fecha de la foto y las alertas con su etiqueta', async () => {
    simularApi(rutas())
    renderConUsuario(<Dashboard />)
    expect(await screen.findByText('Ventas del día')).toBeInTheDocument()
    expect(screen.getByText('31 dic 2025')).toBeInTheDocument()
    expect(screen.getByText('dic 2025')).toBeInTheDocument()
    expect(screen.getByText('$737.9M')).toBeInTheDocument()
    expect(screen.getByText('1.500')).toBeInTheDocument()
    expect(await screen.findByText('Inconsistencia de inventario')).toBeInTheDocument()
    expect(screen.queryByText(/stock critico/)).not.toBeInTheDocument()
    expect(screen.getByText('3.611 OK')).toBeInTheDocument()
    expect(screen.getByText('95 Inconsistencia')).toBeInTheDocument()
    expect(await screen.findByText('Tendencia de ventas (30 días)')).toBeInTheDocument()
    expect(screen.getByText('Top 5 productos')).toBeInTheDocument()
    expect(screen.getByText('Datos al 31 dic 2025')).toBeInTheDocument()
    expect(screen.queryByText('Ventas hoy')).not.toBeInTheDocument()
  })

  it('un bloque que falla no tumba la página', async () => {
    simularApi(rutas({ 'GET /api/reportes/ventas/top-productos': { status: 500 } }))
    renderConUsuario(<Dashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Error del servidor')
    expect(await screen.findByText('Ventas del día')).toBeInTheDocument()
    expect(screen.getByText('Alertas activas')).toBeInTheDocument()
  })

  it('con la Bodega elegida muestra la vista de Bodega y no pide ventas (H1)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Dashboard />)
    const selector = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(screen.getByRole('option', { name: 'Bodega Central' })).toBeInTheDocument())
    await userEvent.selectOptions(selector, '5')
    expect(await screen.findByText(/La Bodega Central no vende/)).toBeInTheDocument()
    expect(await screen.findByText('671')).toBeInTheDocument()
    expect(screen.getByText('$356.0M')).toBeInTheDocument()
    expect(screen.queryByText('Ventas del día')).not.toBeInTheDocument()
    expect(screen.queryByText('Top 5 productos')).not.toBeInTheDocument()
    const deVentas = api.llamadas.filter(l => ['/api/reportes/tendencias', '/api/reportes/ventas/top-productos'].includes(l.ruta))
    expect(deVentas.every(l => l.params.sucursal_id !== '5')).toBe(true)
    expect(api.llamadas.some(l => l.ruta === '/api/alertas/resumen' && l.params.sucursal_id === '5')).toBe(true)
  })

  it('sin ventas en el período lo dice en vez de dejar el bloque vacío', async () => {
    simularApi(rutas({
      'GET /api/reportes/tendencias': { body: { series: [], fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31' } },
      'GET /api/reportes/ventas/top-productos': { body: { items: [] } },
    }))
    renderConUsuario(<Dashboard />)
    await waitFor(() => expect(screen.getAllByText('Sin ventas en el período.')).toHaveLength(2))
  })

  it('el admin_sucursal no tiene selector y consulta su sucursal', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Dashboard />, USUARIOS.adminPrincipal)
    expect(await screen.findByText('Ventas del día')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta.startsWith('/api/reportes')).every(l => l.params.sucursal_id === '1')).toBe(true)
  })

  it('el admin_bodega lo ve como el gerente (H2)', async () => {
    simularApi(rutas())
    renderConUsuario(<Dashboard />, USUARIOS.bodega)
    expect(await screen.findByText('Ventas del día')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Sucursal' })).toBeInTheDocument()
  })
})
