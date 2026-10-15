import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Alertas from './Alertas'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

const alerta = (i, cambios = {}) => ({
  id_producto: i, nombre_producto: `PRODUCTO ${i}`, categoria: 'Arroz', sucursal: 'PRINCIPAL', id_sucursal: 1,
  tipo_ubicacion: 'sucursal', tipo: 'stock_bajo', urgencia: 'alta', valor: 4, umbral: 7, detalle: `detalle ${i}`,
  fecha: '2025-12-31', ...cambios,
})

const MUCHAS = Array.from({ length: 120 }, (_, i) => alerta(i + 1))
MUCHAS[0] = alerta(1, { tipo: 'inconsistencia_inventario', urgencia: 'critica', valor: -44,
  detalle: 'Stock negativo en la foto (-44 uds): verificar el conteo' })
MUCHAS[1] = alerta(2, { sucursal: 'BODEGA_CENTRAL', id_sucursal: 5, tipo_ubicacion: 'bodega_central', tipo: 'stock_critico',
  urgencia: 'critica' })

// Pagina como GET /api/alertas (K2): con page y page_size devuelve esa página
function rutas(items = MUCHAS) {
  return {
    'GET /api/alertas': ({ params }) => {
      const page = Number(params.page), size = Number(params.page_size)
      return { body: { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size,
        pages: Math.ceil(items.length / size), fecha_inventario: '2025-12-31' } }
    },
    'GET /api/alertas/resumen': {
      body: { items: [], global_: { critica: 1334, alta: 386, media: 2732, total: 4452 }, por_tipo: {} },
    },
  }
}

const tarjetas = () => screen.getAllByText(/^detalle \d+$|^Stock negativo/)

describe('Alertas (A3.5)', () => {
  it('pide a la API de a 50 (K2)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('Página 1 de 3 · 120 alertas')).toBeInTheDocument()
    expect(screen.getByText('120 alertas activas · 31 dic 2025')).toBeInTheDocument()
    expect(tarjetas()).toHaveLength(50)
    expect(api.llamadas.find(l => l.ruta === '/api/alertas').params).toEqual({ page: '1', page_size: '50' })
    await userEvent.click(screen.getByLabelText('Página siguiente'))
    await userEvent.click(await screen.findByLabelText('Página siguiente'))
    expect(await screen.findByText('Página 3 de 3 · 120 alertas')).toBeInTheDocument()
    expect(tarjetas()).toHaveLength(20)
    expect(screen.getByLabelText('Página siguiente')).toBeDisabled()
    await userEvent.click(screen.getByLabelText('Página anterior'))
    expect(await screen.findByText('Página 2 de 3 · 120 alertas')).toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas').map(l => l.params.page)).toEqual(['1', '2', '3', '2'])
  })

  it('muestra la inconsistencia con su etiqueta, la urgencia y el distintivo de la Bodega', async () => {
    simularApi(rutas())
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('PRINCIPAL · Inconsistencia de inventario')).toBeInTheDocument()
    const deBodega = screen.getByText('PRODUCTO 2').closest('div').parentElement
    expect(within(deBodega).getByText('Bodega')).toBeInTheDocument()
    expect(screen.getAllByText('Crítica', { selector: 'span' })).toHaveLength(2)
    expect(screen.getByText('4.452')).toBeInTheDocument()
  })

  it('filtra por el tipo nuevo y por urgencia, y vuelve a la primera página', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Alertas />)
    await screen.findByText('Página 1 de 3 · 120 alertas')
    await userEvent.click(screen.getByLabelText('Página siguiente'))
    await screen.findByText('Página 2 de 3 · 120 alertas')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Tipo' }), 'Inconsistencia de inventario')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Urgencia' }), 'Crítica')
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas').at(-1).params)
      .toEqual({ tipo: 'inconsistencia_inventario', urgencia: 'critica', page: '1', page_size: '50' }))
    expect(await screen.findByText('Página 1 de 3 · 120 alertas')).toBeInTheDocument()
  })

  it('sin alertas lo dice; "Actualizar" repite las dos consultas', async () => {
    const api = simularApi(rutas([]))
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('Sin alertas')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Actualizar'))
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas')).toHaveLength(2))
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas/resumen')).toHaveLength(2)
  })

  it('un error se muestra en vez de quedar vacía', async () => {
    simularApi({ 'GET /api/alertas': { status: 403, body: { detail: 'Solo puede consultar su sucursal (PRINCIPAL)' } } })
    renderConUsuario(<Alertas />, USUARIOS.adminPrincipal)
    expect(await screen.findByText('Solo puede consultar su sucursal (PRINCIPAL)')).toBeInTheDocument()
  })

  it('el gerente filtra por ubicación', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Alertas />)
    const selector = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(selector).getAllByRole('option')).toHaveLength(5))
    await userEvent.selectOptions(selector, '3')
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas').at(-1).params)
      .toEqual({ sucursal_id: '3', page: '1', page_size: '50' }))
  })
})

// ── Alertas con IA (INV-28) ─────────────────────────
const alertaIA = (i, cambios = {}) => ({
  id_producto: 1000 + i, codigo_item: `C${i}`, nombre_producto: `IA ${i}`, categoria: 'Huevos', sucursal: 'PRINCIPAL',
  id_sucursal: 1, tipo_ubicacion: 'sucursal', tipo: 'riesgo_desabastecimiento_ml', urgencia: 'critica', origen: 'ml',
  valor: 2.2, umbral: 5, unidad: 'unidad', stock: 489, q50: 3366.01, detalle: `detalle IA ${i}`, fecha: '2025-12-31',
  ...cambios,
})
const IA = Array.from({ length: 60 }, (_, i) => alertaIA(i + 1))
IA[0] = alertaIA(1, { nombre_producto: 'HUEVOS *UND', origen: 'ambos' })
IA[1] = alertaIA(2, { nombre_producto: 'CONDIMENTO EL TIZON * 50 GR', sucursal: 'GLORIETA', id_sucursal: 3,
  tipo: 'sobrestock_previsto_ml', urgencia: 'media', valor: 22, umbral: 2 })

function rutasIA(items = IA, extra = {}) {
  return {
    ...rutas([]),
    'GET /api/alertas/ml': ({ params }) => {
      const page = Number(params.page), size = Number(params.page_size)
      return { body: { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size,
        pages: Math.ceil(items.length / size), resumen: {}, fecha_inventario: '2025-12-31',
        politicas: { version: 1, fecha: '2026-09-30' }, calculado_en: '2026-10-15T15:00:00Z' } }
    },
    ...extra,
  }
}

const seccionIA = () => screen.getByRole('region', { name: 'Alertas con IA' })

describe('Alertas con IA (INV-28)', () => {
  it('muestra la sección con su distintivo, el tipo, el origen y la paginación propia', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('HUEVOS *UND')).toBeInTheDocument()
    const seccion = seccionIA()
    expect(within(seccion).getByText(/60 alertas · 31 dic 2025/)).toBeInTheDocument()
    expect(within(seccion).getByText('PRINCIPAL · Riesgo de desabastecimiento · También por reglas')).toBeInTheDocument()
    expect(within(seccion).getByText('GLORIETA · Sobrestock previsto')).toBeInTheDocument()
    // un distintivo en el título y uno por tarjeta (50 en la página)
    expect(within(seccion).getAllByText('IA')).toHaveLength(51)
    expect(api.llamadas.find(l => l.ruta === '/api/alertas/ml').params).toEqual({ page: '1', page_size: '50' })
    await userEvent.click(within(seccion).getByLabelText('Página siguiente de alertas con IA'))
    expect(await within(seccion).findByText('Página 2 de 2 · 60 alertas')).toBeInTheDocument()
    expect(within(seccion).getAllByText(/^detalle IA \d+$/)).toHaveLength(10)
  })

  it('las de reglas no esperan a las de IA (V1)', async () => {
    simularApi(rutasIA(IA, { 'GET /api/alertas': { body: { items: [alerta(1)], total: 1, page: 1, page_size: 50, pages: 1,
      fecha_inventario: '2025-12-31' } }, 'GET /api/alertas/ml': { body: {}, demoraMs: 60_000 } }))
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('detalle 1')).toBeInTheDocument()
    expect(within(seccionIA()).queryByText(/^detalle IA/)).not.toBeInTheDocument()
  })

  it('filtra por tipo, urgencia y origen, y vuelve a la primera página', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await screen.findByText('HUEVOS *UND')
    await userEvent.click(within(seccionIA()).getByLabelText('Página siguiente de alertas con IA'))
    await within(seccionIA()).findByText('Página 2 de 2 · 60 alertas')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Tipo de alerta con IA' }), 'Sobrestock previsto')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Urgencia de alerta con IA' }), 'Media')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Origen' }), 'Solo IA')
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml').at(-1).params).toEqual({
      tipo: 'sobrestock_previsto_ml', urgencia: 'media', origen: 'ml', page: '1', page_size: '50' }))
  })

  it('un error del ML Service se muestra con "Reintentar" y las de reglas siguen', async () => {
    let n = 0
    const api = simularApi(rutasIA(IA, {
      'GET /api/alertas': { body: { items: [alerta(1)], total: 1, page: 1, page_size: 50, pages: 1,
        fecha_inventario: '2025-12-31' } },
      'GET /api/alertas/ml': () => (++n === 1
        ? { status: 503, body: { detail: 'ML Service no disponible' } }
        : { body: { items: [IA[0]], total: 1, page: 1, page_size: 50, pages: 1, resumen: {},
          fecha_inventario: '2025-12-31', politicas: {}, calculado_en: '' } }),
    }))
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('El servicio no está disponible en este momento.')).toBeInTheDocument()
    expect(screen.getByText('detalle 1')).toBeInTheDocument()
    await userEvent.click(within(seccionIA()).getByText('Reintentar'))
    expect(await screen.findByText('HUEVOS *UND')).toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml')).toHaveLength(2)
  })

  it('sin alertas lo dice y nombra a la Bodega; "Actualizar" también las repite', async () => {
    const api = simularApi(rutasIA([]))
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('Sin alertas con IA')).toBeInTheDocument()
    expect(screen.getByText(/La Bodega Central no genera alertas con IA/)).toBeInTheDocument()
    await userEvent.click(screen.getByText('Actualizar'))
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml')).toHaveLength(2))
  })

  it('un admin_sucursal las pide de su sucursal', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />, USUARIOS.adminNorte)
    await screen.findByText('HUEVOS *UND')
    expect(api.llamadas.find(l => l.ruta === '/api/alertas/ml').params.sucursal_id).toBe('2')
  })

  it('el gerente cambia de sucursal y las de IA vuelven a la primera página', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await screen.findByText('HUEVOS *UND')
    await userEvent.click(within(seccionIA()).getByLabelText('Página siguiente de alertas con IA'))
    await within(seccionIA()).findByText('Página 2 de 2 · 60 alertas')
    const selector = screen.getByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(selector).getAllByRole('option')).toHaveLength(5))
    await userEvent.selectOptions(selector, '3')
    await waitFor(() => expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml').at(-1).params)
      .toEqual({ sucursal_id: '3', page: '1', page_size: '50' }))
  })
})
