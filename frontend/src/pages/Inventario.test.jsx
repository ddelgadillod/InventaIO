import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Inventario from './Inventario'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

const fila = (cambios = {}) => ({
  id_producto: 171, nombre_producto: 'ARROZ ZULIA *500 GR', categoria: 'Arroz', es_perecedero: false,
  sucursal: 'PRINCIPAL', id_sucursal: 1, tipo_ubicacion: 'sucursal', stock_disponible: 556, stock_bodega: 4024,
  stock_minimo: 300, stock_maximo: 1200, punto_reorden: 450, dias_cobertura: 5.3, semaforo: 'bajo',
  fecha: '2025-12-31', ...cambios,
})

const FILAS = [
  fila(),
  fila({ id_producto: 941, nombre_producto: 'CEPILLO LAVA-AUTOS', categoria: 'Aseo hogar', sucursal: 'GLORIETA',
    id_sucursal: 3, stock_disponible: -44, stock_bodega: 20, dias_cobertura: -347.4, semaforo: 'inconsistencia' }),
  fila({ id_producto: 12, nombre_producto: 'VELA SIN VENTAS', categoria: 'Velas y velones', stock_disponible: 12,
    stock_bodega: null, dias_cobertura: 999, semaforo: 'ok' }),
  fila({ id_producto: 171, sucursal: 'BODEGA_CENTRAL', id_sucursal: 5, tipo_ubicacion: 'bodega_central',
    stock_disponible: 4024, stock_bodega: null, dias_cobertura: 30, semaforo: 'ok' }),
]

const CATEGORIAS = {
  items: [{ categoria: 'Licores', total_productos: 300 }, { categoria: 'Arroz', total_productos: 50 },
    { categoria: 'Aceites y sustitutos', total_productos: 80 }],
  total: 3,
}

function rutas(cambios = {}) {
  return {
    'GET /api/consulta/categorias': { body: CATEGORIAS },
    'GET /api/consulta/inventario': ({ params }) => ({
      body: { items: FILAS, total: 45, page: Number(params.page), page_size: 15, pages: 3, fecha_inventario: '2025-12-31' },
    }),
    ...cambios,
  }
}

const celdas = nombre => within(screen.getAllByText(nombre)[0].closest('tr')).getAllByRole('cell').map(c => c.textContent)

describe('Inventario (A3.4)', () => {
  it('ofrece las categorías de la bodega, en orden alfabético', async () => {
    simularApi(rutas())
    renderConUsuario(<Inventario />)
    const select = screen.getByRole('combobox', { name: 'Categoría' })
    await waitFor(() => expect(within(select).getAllByRole('option').map(o => o.textContent))
      .toEqual(['Todas las categorías', 'Aceites y sustitutos', 'Arroz', 'Licores']))
  })

  it('muestra la inconsistencia, "Sin ventas", el stock de la Bodega y su distintivo (H3, G6)', async () => {
    simularApi(rutas())
    renderConUsuario(<Inventario />)
    expect(await screen.findByText('45 productos · 31 dic 2025')).toBeInTheDocument()
    expect(celdas('ARROZ ZULIA *500 GR')).toEqual(
      ['ARROZ ZULIA *500 GR', 'Arroz', 'PRINCIPAL', '556', '4.024', '450', '5,3 d', '⚠ Bajo'])
    expect(celdas('CEPILLO LAVA-AUTOS')).toEqual(
      ['CEPILLO LAVA-AUTOS', 'Aseo hogar', 'GLORIETA', '-44', '20', '450', '—', '◆ Inconsistencia'])
    expect(celdas('VELA SIN VENTAS')).toEqual(
      ['VELA SIN VENTAS', 'Velas y velones', 'PRINCIPAL', '12', '—', '450', 'Sin ventas', '✓ OK'])
    const bodega = within(screen.getByText('BODEGA_CENTRAL').closest('tr')).getAllByRole('cell').map(c => c.textContent)
    expect(bodega.slice(2, 5)).toEqual(['BODEGA_CENTRALBodega', '4.024', '—'])
  })

  it('los productos por kilo llevan un decimal (J5)', async () => {
    simularApi(rutas({
      'GET /api/consulta/inventario': {
        body: { items: [fila({ nombre_producto: 'PAPA PASTUSA *KL', unidad: 'kg', stock_disponible: 77.145,
          stock_bodega: 0, punto_reorden: 86 })], total: 1, page: 1, page_size: 15, pages: 1, fecha_inventario: '2025-12-31' },
      },
    }))
    renderConUsuario(<Inventario />)
    expect((await screen.findAllByRole('cell')).slice(3, 6).map(c => c.textContent)).toEqual(['77,1', '0,0', '86,0'])
  })

  it('filtra por inconsistencia, el estado que entrega la API (K3)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Inventario />)
    await screen.findByText('45 productos · 31 dic 2025')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Estado' }), '◆ Inconsistencia')
    await waitFor(() => expect(api.llamadas.at(-1).params).toMatchObject({ semaforo: 'inconsistencia', page: '1' }))
  })

  it('un filtro nuevo vuelve a la primera página y viaja a la API', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Inventario />)
    await screen.findByText('Página 1 de 3 · 45 total')
    await userEvent.click(screen.getByLabelText('Página siguiente'))
    expect(await screen.findByText('Página 2 de 3 · 45 total')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByRole('option', { name: 'Licores' })).toHaveLength(1))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Categoría' }), 'Licores')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Estado' }), 'critico')
    await waitFor(() => expect(api.llamadas.at(-1).params).toEqual(
      { page: '1', page_size: '15', semaforo: 'critico', categoria: 'Licores' }))
    await userEvent.click(await screen.findByLabelText('Página anterior'))
  })

  it('una búsqueda nueva nunca queda pisada por la respuesta anterior', async () => {
    simularApi(rutas({
      'GET /api/consulta/inventario': ({ params }) => ({
        body: { items: [fila({ nombre_producto: `RESULTADO ${params.busqueda ?? 'INICIAL'}` })], total: 1, page: 1, page_size: 15,
          pages: 1, fecha_inventario: '2025-12-31' },
        demoraMs: params.busqueda === 'ARROZ' ? 80 : 0,
      }),
    }))
    renderConUsuario(<Inventario />)
    await screen.findByText('RESULTADO INICIAL')
    const buscar = screen.getByPlaceholderText('Buscar producto...')
    await userEvent.type(buscar, 'ARROZ{Enter}')
    await userEvent.clear(buscar)
    await userEvent.type(buscar, 'HUEVOS{Enter}')
    expect(await screen.findByText('RESULTADO HUEVOS')).toBeInTheDocument()
    await new Promise(r => setTimeout(r, 120))
    expect(screen.queryByText('RESULTADO ARROZ')).not.toBeInTheDocument()
  })

  it('al elegir un producto abre su detalle (A3.6)', async () => {
    const api = simularApi(rutas({
      'GET /api/consulta/inventario/detalle': { body: { ...fila(), stock_actual: 556, historial: [] } },
      'GET /api/consulta/productos/171': { body: { codigo_item: 'P3937', unidad: 'unidad', proveedores: ['Distribuidora Valle S.A.S.'] } },
    }))
    renderConUsuario(<Inventario />)
    const [dePrincipal] = await screen.findAllByRole('button', { name: 'ARROZ ZULIA *500 GR' })
    await userEvent.click(dePrincipal)
    expect(await screen.findByRole('dialog', { name: 'Detalle de inventario' })).toBeInTheDocument()
    expect(await screen.findByText('Distribuidora Valle S.A.S.')).toBeInTheDocument()
    expect(api.llamadas.find(l => l.ruta === '/api/consulta/inventario/detalle').params).toEqual({ id_producto: '171', id_sucursal: '1' })
    await userEvent.click(screen.getByLabelText('Cerrar detalle'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('muestra el error en vez de quedar vacía, y avisa si no hay resultados', async () => {
    simularApi(rutas({ 'GET /api/consulta/inventario': { status: 503 } }))
    const { unmount } = renderConUsuario(<Inventario />)
    expect(await screen.findByRole('alert')).toHaveTextContent('El servicio no está disponible')
    unmount()
    simularApi(rutas({
      'GET /api/consulta/inventario': { body: { items: [], total: 0, page: 1, page_size: 15, pages: 0, fecha_inventario: '2025-12-31' } },
    }))
    renderConUsuario(<Inventario />)
    expect(await screen.findByText('No hay productos que coincidan con los filtros.')).toBeInTheDocument()
  })

  it('el admin_sucursal consulta su sucursal, sin selector; el gerente puede elegir', async () => {
    const api = simularApi(rutas())
    const { unmount } = renderConUsuario(<Inventario />, USUARIOS.adminPrincipal)
    await screen.findByText('45 productos · 31 dic 2025')
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).not.toBeInTheDocument()
    expect(api.llamadas.find(l => l.ruta === '/api/consulta/inventario').params.sucursal_id).toBe('1')
    unmount()
    renderConUsuario(<Inventario />, USUARIOS.gerente)
    const selector = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(selector).getAllByRole('option')).toHaveLength(5))
    await userEvent.selectOptions(selector, '5')
    await waitFor(() => expect(api.llamadas.at(-1).params).toMatchObject({ sucursal_id: '5', page: '1' }))
  })
})
