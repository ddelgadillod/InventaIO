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

// V13: los filtros son desplegables con casillas
async function marcar(etiqueta, ...opciones) {
  await userEvent.click(screen.getByRole('button', { name: new RegExp(`^${etiqueta}:`) }))
  const grupo = screen.getByRole('group', { name: etiqueta })
  for (const opcion of opciones) await userEvent.click(within(grupo).getByLabelText(opcion))
  await userEvent.keyboard('{Escape}')
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
    await marcar('Tipo', 'Inconsistencia de inventario')
    await marcar('Urgencia', 'Crítica')
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
IA[0] = alertaIA(1, { nombre_producto: 'HUEVOS *UND', origen: 'ambos', accion: 'traslado_y_compra' })
IA[1] = alertaIA(2, { nombre_producto: 'CONDIMENTO EL TIZON * 50 GR', sucursal: 'GLORIETA', id_sucursal: 3,
  tipo: 'sobrestock_previsto_ml', urgencia: 'media', valor: 22, umbral: 2 })

function rutasIA(items = IA, extra = {}) {
  return {
    ...rutas([]),
    'GET /api/alertas/ml': ({ params }) => {
      const page = Number(params.page), size = Number(params.page_size)
      const resumen = {
        total: items.length, riesgo_desabastecimiento_ml: items.filter(a => a.tipo === 'riesgo_desabastecimiento_ml').length,
        sobrestock_previsto_ml: items.filter(a => a.tipo === 'sobrestock_previsto_ml').length,
        ambos: items.filter(a => a.origen === 'ambos').length,
      }
      return { body: { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size,
        pages: Math.ceil(items.length / size), resumen, fecha_inventario: '2025-12-31', fecha_pronostico: '2025-12-31',
        politicas: { version: 1, fecha: '2026-09-30' }, calculado_en: '2026-10-15T15:00:00Z' } }
    },
    'GET /api/consulta/categorias': { body: { items: [{ categoria: 'Lácteos' }, { categoria: 'Arroz' }, { categoria: 'Huevos' }] } },
    ...extra,
  }
}

const panelIA = () => screen.getByRole('tabpanel', { name: 'Alertas con IA' })
const llamadasIA = (api, size = '50') => api.llamadas.filter(l => l.ruta === '/api/alertas/ml' && l.params.page_size === size)
async function abrirIA() {
  await userEvent.click(screen.getByRole('tab', { name: 'Con IA' }))
}

describe('Alertas con IA (INV-28, pestañas V12)', () => {
  it('por defecto muestra las de reglas y no consulta las de IA', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    expect(await screen.findByText('Sin alertas')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Por reglas' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Con IA' })).toHaveAttribute('aria-selected', 'false')
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml')).toHaveLength(0)
  })

  it('la pestaña Con IA trae su resumen, el distintivo, el tipo, el origen y la paginación', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await screen.findByText('Sin alertas')
    const antes = api.llamadas.filter(l => l.ruta === '/api/alertas').length
    await abrirIA()
    expect(await screen.findByText('HUEVOS *UND')).toBeInTheDocument()
    const panel = panelIA()
    expect(within(panel).getByText(/^60 alertas · foto del 31 dic 2025 · pronóstico con datos al 31 dic 2025$/)).toBeInTheDocument()
    expect(within(panel).getByText('Riesgo de desabastecimiento', { selector: 'p' }).previousSibling).toHaveTextContent('59')
    expect(within(panel).getByText('Sobrestock previsto', { selector: 'p' }).previousSibling).toHaveTextContent('1')
    expect(within(panel).getByText('También por reglas', { selector: 'p' }).previousSibling).toHaveTextContent('1')
    expect(within(panel).getByText('PRINCIPAL · Riesgo de desabastecimiento · También por reglas · Acción: Traslado y compra')).toBeInTheDocument()
    expect(within(panel).getByText('GLORIETA · Sobrestock previsto')).toBeInTheDocument()
    expect(within(panel).getAllByText('IA')).toHaveLength(50)
    expect(screen.queryByRole('tabpanel', { name: 'Alertas por reglas' })).not.toBeInTheDocument()
    expect(llamadasIA(api)[0].params).toEqual({ page: '1', page_size: '50' })
    expect(llamadasIA(api, '1')).toHaveLength(1)
    await userEvent.click(within(panel).getByLabelText('Página siguiente'))
    expect(await within(panel).findByText('Página 2 de 2 · 60 alertas')).toBeInTheDocument()
    expect(within(panel).getAllByText(/^detalle IA \d+$/)).toHaveLength(10)
    // La pestaña cerrada no se consulta
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas')).toHaveLength(antes)
  })

  it('filtra por tipo, urgencia y origen, vuelve a la primera página y el resumen no cambia', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    await userEvent.click(within(panelIA()).getByLabelText('Página siguiente'))
    await within(panelIA()).findByText('Página 2 de 2 · 60 alertas')
    await marcar('Tipo de alerta con IA', 'Sobrestock previsto')
    await marcar('Urgencia de alerta con IA', 'Media')
    await marcar('Origen', 'Solo IA')
    await waitFor(() => expect(llamadasIA(api).at(-1).params).toEqual({
      tipo: 'sobrestock_previsto_ml', urgencia: 'media', origen: 'ml', page: '1', page_size: '50' }))
    expect(llamadasIA(api, '1')).toHaveLength(1)
  })

  it('cada pestaña conserva sus filtros al cambiar de una a otra', async () => {
    simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await screen.findByText('Sin alertas')
    await marcar('Urgencia', 'Crítica')
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    await marcar('Origen', 'También por reglas')
    await userEvent.click(screen.getByRole('tab', { name: 'Por reglas' }))
    expect(await screen.findByRole('button', { name: 'Urgencia: Crítica' })).toBeInTheDocument()
    await abrirIA()
    expect(await screen.findByRole('button', { name: 'Origen: También por reglas' })).toBeInTheDocument()
  })

  it('un error del ML Service se muestra una vez y "Reintentar" repite la lista y el resumen', async () => {
    let n = 0
    const api = simularApi(rutasIA(IA, {
      'GET /api/alertas/ml': ({ params }) => (++n <= 2
        ? { status: 503, body: { detail: 'ML Service no disponible' } }
        : { body: { items: params.page_size === '1' ? [] : [IA[0]], total: 1, page: 1, page_size: 50, pages: 1,
          resumen: { total: 1, riesgo_desabastecimiento_ml: 1, sobrestock_previsto_ml: 0, ambos: 1 },
          fecha_inventario: '2025-12-31', politicas: {}, calculado_en: '' } }),
    }))
    renderConUsuario(<Alertas />)
    await abrirIA()
    expect(await screen.findAllByText('El servicio no está disponible en este momento.')).toHaveLength(1)
    await userEvent.click(within(panelIA()).getByText('Reintentar'))
    expect(await screen.findByText('HUEVOS *UND')).toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas/ml')).toHaveLength(4)
    expect(within(panelIA()).getByText('Total').previousSibling).toHaveTextContent('1')
  })

  it('sin alertas lo dice y nombra a la Bodega; "Actualizar" repite solo la pestaña abierta', async () => {
    const api = simularApi(rutasIA([]))
    renderConUsuario(<Alertas />)
    await screen.findByText('Sin alertas')
    await abrirIA()
    expect(await screen.findByText('Sin alertas con IA')).toBeInTheDocument()
    expect(screen.getByText(/La Bodega Central no genera alertas con IA/)).toBeInTheDocument()
    const reglas = api.llamadas.filter(l => l.ruta === '/api/alertas').length
    await userEvent.click(screen.getByText('Actualizar'))
    await waitFor(() => expect(llamadasIA(api)).toHaveLength(2))
    expect(llamadasIA(api, '1')).toHaveLength(2)
    expect(api.llamadas.filter(l => l.ruta === '/api/alertas')).toHaveLength(reglas)
  })

  it('un admin_sucursal las pide de su sucursal', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />, USUARIOS.adminNorte)
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    expect(llamadasIA(api)[0].params.sucursal_id).toBe('2')
  })

  it('el gerente cambia de sucursal y las de IA vuelven a la primera página', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    const selector = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(selector).getAllByRole('option')).toHaveLength(5))
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    await userEvent.click(within(panelIA()).getByLabelText('Página siguiente'))
    await within(panelIA()).findByText('Página 2 de 2 · 60 alertas')
    await userEvent.selectOptions(selector, '3')
    await waitFor(() => expect(llamadasIA(api).at(-1).params).toEqual({ sucursal_id: '3', page: '1', page_size: '50' }))
    expect(llamadasIA(api, '1').at(-1).params.sucursal_id).toBe('3')
  })
})

describe('Filtros con varios valores (INV-28, V13)', () => {
  it('reglas: marca dos tipos y dos urgencias y los manda repetidos', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Alertas />)
    await screen.findByText('Página 1 de 3 · 120 alertas')
    await marcar('Tipo', 'Stock crítico', 'Stock bajo')
    await marcar('Urgencia', 'Crítica', 'Alta')
    expect(screen.getByRole('button', { name: 'Tipo: 2 tipos' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Urgencia: 2 urgencias' })).toBeInTheDocument()
    await waitFor(() => {
      const u = new URL(api.fetch.mock.calls.filter(([url]) => String(url).includes('/api/alertas?')).at(-1)[0], 'http://x')
      expect(u.searchParams.getAll('tipo')).toEqual(['stock_critico', 'stock_bajo'])
      expect(u.searchParams.getAll('urgencia')).toEqual(['critica', 'alta'])
      expect(u.searchParams.get('page')).toBe('1')
    })
  })

  it('IA: desmarcar todo vuelve a "todos" y no manda el filtro', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    await marcar('Urgencia de alerta con IA', 'Crítica', 'Alta')
    await waitFor(() => {
      const u = new URL(api.fetch.mock.calls.filter(([url]) => String(url).includes('page_size=50')).at(-1)[0], 'http://x')
      expect(u.searchParams.getAll('urgencia')).toEqual(['critica', 'alta'])
    })
    await marcar('Urgencia de alerta con IA', 'Crítica', 'Alta')
    expect(screen.getByRole('button', { name: 'Urgencia de alerta con IA: Todas las urgencias' })).toBeInTheDocument()
    await waitFor(() => expect(llamadasIA(api).at(-1).params).toEqual({ page: '1', page_size: '50' }))
  })
})

describe('Conciliación con la ficha de Jira (INV-28, V14)', () => {
  it('filtra por categoría con las de la bodega, en orden alfabético', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await abrirIA()
    await screen.findByText('HUEVOS *UND')
    await userEvent.click(screen.getByRole('button', { name: /^Categoría:/ }))
    const grupo = screen.getByRole('group', { name: 'Categoría' })
    expect(within(grupo).getAllByRole('checkbox').map(c => c.parentElement.textContent)).toEqual(['Arroz', 'Huevos', 'Lácteos'])
    await userEvent.click(within(grupo).getByLabelText('Huevos'))
    await userEvent.click(within(grupo).getByLabelText('Arroz'))
    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Categoría: 2 categorías' })).toBeInTheDocument()
    await waitFor(() => {
      const u = new URL(api.fetch.mock.calls.filter(([url]) => String(url).includes('page_size=50')).at(-1)[0], 'http://x')
      expect(u.searchParams.getAll('categoria')).toEqual(['Arroz', 'Huevos'])
      expect(u.searchParams.get('page')).toBe('1')
    })
  })

  it('las categorías no se piden mientras la pestaña de IA está cerrada', async () => {
    const api = simularApi(rutasIA())
    renderConUsuario(<Alertas />)
    await screen.findByText('Sin alertas')
    expect(api.llamadas.filter(l => l.ruta === '/api/consulta/categorias')).toHaveLength(0)
  })
})
