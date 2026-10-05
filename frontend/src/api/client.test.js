import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from './client'
import { ApiError, getTokens, setTokens, textoDetalle } from './client'
import { simularApi } from '../test/utils'

const rechazo = async promesa => {
  try {
    await promesa
  } catch (err) {
    return err
  }
  throw new Error('se esperaba un error')
}

describe('ApiError (A2.1)', () => {
  it.each([400, 403, 409, 504])('expone el código %i y el detail', async status => {
    simularApi({ 'GET /api/consulta/categorias': { status, body: { detail: `falló con ${status}` } } })
    const err = await rechazo(client.getCategorias())
    expect(err).toBeInstanceOf(ApiError)
    expect([err.status, err.detail, err.message]).toEqual([status, `falló con ${status}`, `falló con ${status}`])
  })

  it('convierte en texto el detail de un 422 de validación', async () => {
    simularApi({
      'GET /api/consulta/productos/91/ventas': {
        status: 422,
        body: { detail: [{ loc: ['query', 'ventanas'], msg: 'Input should be less than or equal to 24' }] },
      },
    })
    const err = await rechazo(client.getVentasProducto(91, { sucursalId: 1, ventanas: 25 }))
    expect(err.status).toBe(422)
    expect(err.detail).toBe('ventanas: Input should be less than or equal to 24')
  })

  it('textoDetalle sin detail usa el código, y sin campo deja solo el mensaje', () => {
    expect(textoDetalle(undefined, 502)).toBe('Error 502')
    expect(textoDetalle([{ loc: ['body'], msg: 'Field required' }, { msg: 'otro' }], 422)).toBe('Field required; otro')
  })

  it('sin conexión responde status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await rechazo(client.getSucursales())
    expect([err.status, err.message, err.cancelada, err.timeout]).toEqual([0, 'No hay conexión con el servidor', false, false])
  })
})

describe('timeout y cancelación (A2.3)', () => {
  it('corta las consultas de ML a los 130 s y lo marca como timeout', async () => {
    vi.useFakeTimers()
    simularApi({ 'GET /api/ml/recomendaciones/compras': { body: {}, demoraMs: 200_000 } })
    const promesa = rechazo(client.getRecomendacionesCompras({ sucursal: 'PRINCIPAL' }))
    await vi.advanceTimersByTimeAsync(client.TIMEOUT_ML_MS)
    const err = await promesa
    expect([err.status, err.timeout, err.message]).toEqual([0, true, 'La consulta tardó más de 130 s'])
  })

  it('una petición nueva con la misma clave cancela la anterior', async () => {
    let n = 0
    simularApi({ 'GET /api/consulta/categorias': () => ({ body: { n: ++n }, demoraMs: n === 1 ? 50 : 0 }) })
    const primera = rechazo(client.getCategorias({ clave: 'categorias' }))
    const segunda = client.getCategorias({ clave: 'categorias' })
    expect(await segunda).toEqual({ n: 2 })
    const err = await primera
    expect([err.cancelada, err.status]).toEqual([true, 0])
  })

  it('una señal externa cancela la petición', async () => {
    simularApi({ 'GET /api/consulta/categorias': { body: {}, demoraMs: 50 } })
    const controller = new AbortController()
    const promesa = rechazo(client.getCategorias({ signal: controller.signal }))
    controller.abort()
    expect((await promesa).cancelada).toBe(true)
    const yaCancelada = rechazo(client.getCategorias({ signal: controller.signal }))
    expect((await yaCancelada).cancelada).toBe(true)
  })
})

describe('sesión', () => {
  const ubicacion = window.location

  afterEach(() => {
    Object.defineProperty(window, 'location', { value: ubicacion, configurable: true })
  })

  it('con 401 renueva el token y repite la petición', async () => {
    setTokens('viejo', 'refresco')
    let intentos = 0
    const api = simularApi({
      'GET /api/auth/me': () => (++intentos === 1 ? { status: 401 } : { body: { rol: 'gerente' } }),
      'POST /api/auth/refresh': { body: { access_token: 'nuevo', refresh_token: 'refresco2' } },
    })
    expect(await client.getProfile()).toEqual({ rol: 'gerente' })
    expect(api.llamadas.map(l => l.headers.Authorization).filter(Boolean)).toEqual(['Bearer viejo', 'Bearer nuevo'])
    expect(getTokens()).toEqual({ access: 'nuevo', refresh: 'refresco2' })
  })

  it('si no puede renovar, borra la sesión y manda al login', async () => {
    Object.defineProperty(window, 'location', { value: { href: '/inventario' }, configurable: true })
    setTokens('viejo', 'refresco')
    simularApi({ 'GET /api/auth/me': { status: 401 }, 'POST /api/auth/refresh': { status: 401 } })
    const err = await rechazo(client.getProfile())
    expect([err.status, err.message]).toEqual([401, 'Sesión expirada'])
    expect(getTokens()).toEqual({ access: null, refresh: null })
    expect(window.location.href).toBe('/login')
  })

  it('sin refresh token no intenta renovar', async () => {
    Object.defineProperty(window, 'location', { value: { href: '/' }, configurable: true })
    const api = simularApi({ 'GET /api/auth/me': { status: 401 } })
    expect((await rechazo(client.getProfile())).status).toBe(401)
    expect(api.llamadas).toHaveLength(1)
  })

  it('si la renovación falla por red, también cierra la sesión', async () => {
    Object.defineProperty(window, 'location', { value: { href: '/' }, configurable: true })
    setTokens('viejo', 'refresco')
    vi.stubGlobal('fetch', vi.fn(async url => {
      if (url.endsWith('/auth/refresh')) throw new TypeError('Failed to fetch')
      return new Response('{}', { status: 401 })
    }))
    expect((await rechazo(client.getProfile())).status).toBe(401)
  })

  it('login guarda los tokens; con error usa el detail o "Credenciales inválidas"', async () => {
    simularApi({ 'POST /api/auth/login': { body: { access_token: 'a', refresh_token: 'r' } } })
    await client.login('gerente@inventaio.co', 'admin123')
    expect(getTokens()).toEqual({ access: 'a', refresh: 'r' })

    simularApi({ 'POST /api/auth/login': { status: 403, body: { detail: 'Cuenta desactivada. Contacte al administrador.' } } })
    expect((await rechazo(client.login('x', 'y'))).message).toBe('Cuenta desactivada. Contacte al administrador.')
    simularApi({ 'POST /api/auth/login': { status: 500, body: {} } })
    expect((await rechazo(client.login('x', 'y'))).message).toBe('Credenciales inválidas')
  })

  it('logout borra los tokens aunque el Core API falle', async () => {
    setTokens('a', 'r')
    const api = simularApi({ 'POST /api/auth/logout': { status: 500 } })
    await client.logout()
    expect(api.llamadas[0].body).toEqual({ refresh_token: 'r' })
    expect(getTokens()).toEqual({ access: null, refresh: null })
  })
})

describe('funciones de la API (A2.2)', () => {
  it.each([
    ['getProfile', () => client.getProfile(), 'GET', '/api/auth/me', {}],
    ['getSucursales', () => client.getSucursales(), 'GET', '/api/consulta/sucursales', {}],
    ['getCategorias', () => client.getCategorias(), 'GET', '/api/consulta/categorias', {}],
    ['getProductos', () => client.getProductos({ busqueda: 'ARROZ', pageSize: 20 }), 'GET', '/api/consulta/productos',
      { busqueda: 'ARROZ', page_size: '20' }],
    ['getProducto', () => client.getProducto(91), 'GET', '/api/consulta/productos/91', {}],
    ['getVentasProducto', () => client.getVentasProducto(91, { sucursalId: 1, ventanas: 8 }), 'GET',
      '/api/consulta/productos/91/ventas', { sucursal_id: '1', ventanas: '8' }],
    ['getKPIs', () => client.getKPIs(2), 'GET', '/api/reportes/kpis', { sucursal_id: '2' }],
    ['getVentasTendencia del Dashboard', () => client.getVentasTendencia({ dias: 30, sucursalId: null }), 'GET',
      '/api/reportes/tendencias', { dias: '30' }],
    ['getVentasTendencia de Reportes', () => client.getVentasTendencia({ fechaInicio: '2025-01-01', fechaFin: '2025-12-31',
      categoria: 'Licores', agrupacion: 'mes', porSucursal: true }), 'GET', '/api/reportes/tendencias',
      { fecha_inicio: '2025-01-01', fecha_fin: '2025-12-31', categoria: 'Licores', agrupacion: 'mes', por_sucursal: 'true' }],
    ['getVentas', () => client.getVentas({ fechaInicio: '2025-12-01', fechaFin: '2025-12-31', sucursalId: 2, agrupacion: 'dia' }),
      'GET', '/api/reportes/ventas', { fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31', sucursal_id: '2', agrupacion: 'dia' }],
    ['getComparativa', () => client.getComparativa({ fechaInicio: '2025-12-01', fechaFin: '2025-12-31', categoria: 'Arroz' }),
      'GET', '/api/reportes/ventas/comparativa', { fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31', categoria: 'Arroz' }],
    ['getDistribucionCategorias', () => client.getDistribucionCategorias({ fechaInicio: '2025-12-01', fechaFin: '2025-12-31',
      categoria: 'Arroz' }), 'GET', '/api/reportes/distribucion-categorias', { fecha_inicio: '2025-12-01', fecha_fin: '2025-12-31' }],
    ['getValorizado', () => client.getValorizado(5), 'GET', '/api/consulta/inventario/valorizado', { sucursal_id: '5' }],
    ['getTopProductos', () => client.getTopProductos(5, 3), 'GET', '/api/reportes/ventas/top-productos',
      { limite: '5', sucursal_id: '3' }],
    ['getInventarioResumen', () => client.getInventarioResumen(5), 'GET', '/api/consulta/inventario/resumen',
      { sucursal_id: '5' }],
    ['getInventario', () => client.getInventario({ page: 2, semaforo: '', sucursal_id: null }), 'GET',
      '/api/consulta/inventario', { page: '2' }],
    ['getInventarioDetalle', () => client.getInventarioDetalle(171, 1), 'GET', '/api/consulta/inventario/detalle',
      { id_producto: '171', id_sucursal: '1' }],
    ['getAlertasResumen', () => client.getAlertasResumen(), 'GET', '/api/alertas/resumen', {}],
    ['getAlertas', () => client.getAlertas({ tipo: 'stock_bajo', sucursalId: 3, page: 2, pageSize: 50 }), 'GET', '/api/alertas',
      { tipo: 'stock_bajo', sucursal_id: '3', page: '2', page_size: '50' }],
    ['getAlertas sin página', () => client.getAlertas(), 'GET', '/api/alertas', {}],
    ['getRecomendacionesTransferencias',
      () => client.getRecomendacionesTransferencias({ sucursal: 'GLORIETA', incluirBalance: true }), 'GET',
      '/api/ml/recomendaciones/transferencias', { sucursal: 'GLORIETA', incluir_balance: 'true' }],
  ])('%s', async (_, llamar, metodo, ruta, params) => {
    const api = simularApi({ [`${metodo} ${ruta}`]: { body: { ok: true } } })
    expect(await llamar()).toEqual({ ok: true })
    expect(api.llamadas[0]).toMatchObject({ metodo, ruta, params })
  })

  it('predecir manda los ids y el horizonte de 15 días (G2)', async () => {
    const api = simularApi({ 'POST /api/ml/predict': { body: { prediccion_q50: 3366.01 } } })
    await client.predecir({ idProducto: 91, idSucursal: 1 })
    expect(api.llamadas[0].body).toEqual({ id_producto: 91, id_sucursal: 1, horizonte: 15 })
    expect(api.llamadas[0].headers['Content-Type']).toBe('application/json')
  })

  it('las recomendaciones van por nombre de sucursal', async () => {
    const api = simularApi({ 'GET /api/ml/recomendaciones/compras': { body: {} } })
    await client.getRecomendacionesCompras({ sucursal: 'LA 21', incluirDetalle: false })
    expect(api.fetch.mock.calls[0][0]).toBe('/api/ml/recomendaciones/compras?sucursal=LA+21&incluir_detalle=false')
  })

  it('cambiarPassword hace PATCH con la actual y la nueva', async () => {
    const api = simularApi({ 'PATCH /api/auth/password': { body: { message: 'ok' } } })
    await client.cambiarPassword('admin123', 'nuevaClave1')
    expect(api.llamadas[0].body).toEqual({ current_password: 'admin123', new_password: 'nuevaClave1' })
  })

  it('manda el token guardado', async () => {
    setTokens('token-1', 'r')
    const api = simularApi()
    await client.getSucursales()
    expect(api.llamadas[0].headers.Authorization).toBe('Bearer token-1')
  })

  it('getVentas sin filtros pide el mes de la última venta (el rango de datos de Reportes)', async () => {
    const api = simularApi({ 'GET /api/reportes/ventas': { body: {} } })
    await client.getVentas()
    expect(api.llamadas[0].params).toEqual({})
  })
})
