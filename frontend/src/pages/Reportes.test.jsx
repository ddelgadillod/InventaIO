import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Reportes from './Reportes'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

const RANGO = { datos_desde: '2022-01-02', datos_hasta: '2025-12-31' }
const CATEGORIAS = Array.from({ length: 10 }, (_, i) => ({ categoria: `Categoría ${i + 1}`, participacion_pct: 10 - i, valor_total: 1 }))
CATEGORIAS[0] = { categoria: 'Licores', participacion_pct: 15.36, valor_total: 113315887.56 }

const VALORIZADO = {
  total_valor: 958834997.785, fecha_inventario: '2025-12-31',
  items: [
    { sucursal: 'PRINCIPAL', id_sucursal: 1, tipo_ubicacion: 'sucursal', categoria: 'Licores', valor_stock: 200000000 },
    { sucursal: 'PRINCIPAL', id_sucursal: 1, tipo_ubicacion: 'sucursal', categoria: 'Arroz', valor_stock: 150588181 },
    { sucursal: 'BODEGA_CENTRAL', id_sucursal: 5, tipo_ubicacion: 'bodega_central', categoria: 'Arroz', valor_stock: 355986371 },
  ],
}

function rutas(cambios = {}) {
  return {
    'GET /api/reportes/ventas': ({ params }) => ({
      body: {
        items: [{ periodo: '2025-12-30', cantidad: 10, valor_total: 30000000, costo_total: 1, margen: 1, transacciones: 900 },
          { periodo: '2025-12-31', cantidad: 12, valor_total: 56756777, costo_total: 1, margen: 1, transacciones: 1100 }],
        total_cantidad: 148896.149, total_valor: 737879055.35, total_margen: 149664794.88,
        agrupacion: params.agrupacion ?? 'dia', fecha_inicio: params.fecha_inicio ?? '2025-12-01',
        fecha_fin: params.fecha_fin ?? '2025-12-31', ...RANGO,
      },
    }),
    'GET /api/reportes/ventas/comparativa': {
      body: { resumen: { periodo_actual: '2025-12-01 / 2025-12-31', periodo_anterior: '2025-10-31 / 2025-11-30',
        valor_actual: 737879055.35, valor_anterior: 491678966.08, variacion_pct: 50.1, cantidad_actual: 1, cantidad_anterior: 1 },
      detalle: [], agrupacion: 'dia' },
    },
    'GET /api/reportes/distribucion-categorias': { body: { items: CATEGORIAS, total_valor: 737879055.35 } },
    'GET /api/reportes/tendencias': {
      body: { series: ['GLORIETA', 'LA 21', 'PRINCIPAL'].map(s => ({ sucursal: s, puntos: [
        { fecha: '2025-12-30', valor_total: 1000000, cantidad: 1 }, { fecha: '2025-12-31', valor_total: 2000000, cantidad: 1 }] })),
      fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31' },
    },
    'GET /api/consulta/inventario/valorizado': { body: VALORIZADO },
    'GET /api/consulta/categorias': { body: { items: [{ categoria: 'Licores' }, { categoria: 'Arroz' }], total: 2 } },
    ...cambios,
  }
}

const deVentas = api => api.llamadas.filter(l => l.ruta === '/api/reportes/ventas' && l.params.fecha_inicio)

describe('Reportes (A9)', () => {
  it('abre con el mes de la última venta y los cinco bloques', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    expect(await screen.findByText('Valor vendido')).toBeInTheDocument()
    expect(screen.getByText('1 dic 2025 – 31 dic 2025')).toBeInTheDocument()
    expect(screen.getAllByText('$737.9M').length).toBeGreaterThan(0)
    expect(screen.getByText('2.000')).toBeInTheDocument()                                  // transacciones
    expect(await screen.findByText('31 oct 2025 – 30 nov 2025')).toBeInTheDocument()
    expect(screen.getByText('50.1%')).toBeInTheDocument()
    expect(screen.getByText('15.4%')).toBeInTheDocument()                                  // como las variaciones
    expect(screen.getByText('Y 2 categorías más.')).toBeInTheDocument()
    expect(screen.getByText('Tendencia por sucursal')).toBeInTheDocument()
    expect(screen.getByText(/Foto del 31 dic 2025/)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: /^Bodega Central/ })).toBeInTheDocument()
    expect(deVentas(api)[0].params).toEqual({ fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31', agrupacion: 'dia' })
    expect(api.llamadas.find(l => l.ruta === '/api/reportes/tendencias').params).toMatchObject({ por_sucursal: 'true' })
  })

  it.each([
    ['Trimestre', '2025-10-01', 'semana'],
    ['Año', '2025-01-01', 'mes'],
  ])('el atajo %s pide desde el %s agrupado por %s', async (atajo, desde, agrupacion) => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    await userEvent.click(await screen.findByRole('button', { name: atajo }))
    await waitFor(() => expect(deVentas(api).at(-1).params).toEqual({ fecha_inicio: desde, fecha_fin: '2025-12-31', agrupacion }))
    expect(screen.getByRole('button', { name: atajo })).toHaveAttribute('aria-pressed', 'true')
  })

  it('con toda la historia no hay comparativa', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    await userEvent.click(await screen.findByRole('button', { name: 'Todo' }))
    expect(await screen.findByText(/No aplica a toda la historia/)).toBeInTheDocument()
    await waitFor(() => expect(deVentas(api).at(-1).params.fecha_inicio).toBe('2022-01-02'))
    expect(api.llamadas.filter(l => l.ruta === '/api/reportes/ventas/comparativa' && l.params.fecha_inicio === '2022-01-02')).toHaveLength(0)
  })

  it('el rango libre y su validación', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    const desde = await screen.findByLabelText('Desde')
    fireEvent.change(desde, { target: { value: '2025-12-15' } })
    await waitFor(() => expect(deVentas(api).at(-1).params.fecha_inicio).toBe('2025-12-15'))
    expect(screen.getByText('15 dic 2025 – 31 dic 2025')).toBeInTheDocument()
    const llamadas = deVentas(api).length
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2025-12-01' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('La fecha inicial es posterior a la final')
    expect(deVentas(api)).toHaveLength(llamadas)
  })

  it('la categoría filtra ventas, comparativa, tendencia y valorizado', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    const select = await screen.findByRole('combobox', { name: 'Categoría' })
    await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(3))
    await userEvent.selectOptions(select, 'Licores')
    for (const ruta of ['/api/reportes/ventas', '/api/reportes/ventas/comparativa', '/api/reportes/tendencias']) {
      await waitFor(() => expect(api.llamadas.filter(l => l.ruta === ruta).at(-1).params.categoria).toBe('Licores'))
    }
    expect(await screen.findByText(/Foto del 31 dic 2025 · Licores/)).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Categoría' })).not.toBeInTheDocument()
  })

  it('cambia la agrupación sin cambiar el período', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Agrupación' }), 'Semana')
    await waitFor(() => expect(deVentas(api).at(-1).params).toEqual({ fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31', agrupacion: 'semana' }))
  })

  it('con la Bodega solo muestra el valorizado (K5)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />)
    const selector = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(selector).getAllByRole('option')).toHaveLength(5))
    await userEvent.selectOptions(selector, '5')
    expect(await screen.findByText(/La Bodega Central no vende/)).toBeInTheDocument()
    expect(screen.queryByText('Valor vendido')).not.toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta.startsWith('/api/reportes') && l.params.sucursal_id === '5')).toHaveLength(0)
    await waitFor(() => expect(api.llamadas.some(l => l.ruta === '/api/consulta/inventario/valorizado' && l.params.sucursal_id === '5')).toBe(true))
  })

  it('el admin_sucursal ve su sucursal sin selector', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Reportes />, USUARIOS.adminPrincipal)
    await screen.findByText('Valor vendido')
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).not.toBeInTheDocument()
    expect(deVentas(api).every(l => l.params.sucursal_id === '1')).toBe(true)
  })

  it('un bloque que falla no tumba los demás, y sin ventas lo dice', async () => {
    simularApi(rutas({
      'GET /api/reportes/distribucion-categorias': { status: 500 },
      'GET /api/reportes/tendencias': { body: { series: [], fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31' } },
    }))
    renderConUsuario(<Reportes />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Error del servidor')
    expect(screen.getByText('Valor vendido')).toBeInTheDocument()
    expect(await screen.findByText('Sin ventas en el período.')).toBeInTheDocument()
  })

  it('sin ventas en el período', async () => {
    simularApi(rutas({
      'GET /api/reportes/ventas': ({ params }) => ({ body: { items: [], total_cantidad: 0, total_valor: 0, total_margen: 0,
        agrupacion: 'dia', fecha_inicio: params.fecha_inicio ?? '2025-12-01', fecha_fin: '2025-12-31', ...RANGO } }),
      'GET /api/reportes/distribucion-categorias': { body: { items: [], total_valor: 0 } },
    }))
    renderConUsuario(<Reportes />)
    await waitFor(() => expect(screen.getAllByText('Sin ventas en el período.')).toHaveLength(2))
  })
})
