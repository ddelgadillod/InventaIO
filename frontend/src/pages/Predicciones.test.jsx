import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Predicciones from './Predicciones'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

// Respuestas reales del Core API, foto y features al 2025-12-31
// (docs/INV-26-27-requerimientos.md, Fase B)
const PRODUCTOS = {
  91: { id_producto: 91, codigo_item: 'P1632', nombre: 'HUEVOS *UND', categoria: 'Huevos', unidad: 'unidad' },
  171: { id_producto: 171, codigo_item: 'P3937', nombre: 'ARROZ ZULIA *500 GR', categoria: 'Arroz', unidad: 'unidad' },
  321: { id_producto: 321, codigo_item: 'P1814', nombre: 'PAPA PASTUSA *KL', categoria: 'Frutas y verduras', unidad: 'kg' },
  3367: { id_producto: 3367, codigo_item: '02458', nombre: 'FRIJOL CARGAMANTO GRANOS DEL ORIENTE * 460 GR',
    categoria: 'Granos', unidad: 'unidad' },
}
const FECHAS = [['2025-09-02', '2025-09-16'], ['2025-09-17', '2025-10-02'], ['2025-10-03', '2025-10-17'],
  ['2025-10-18', '2025-11-01'], ['2025-11-02', '2025-11-16'], ['2025-11-17', '2025-12-01'], ['2025-12-02', '2025-12-16'],
  ['2025-12-17', '2025-12-31']]
const ventanas = unidades => FECHAS.map(([desde, hasta], i) => ({ desde, hasta, unidades: unidades[i] }))

const prediccion = (id, sucursal, rama, q50, limite, alpha, interpretacion) => ({
  producto_id: PRODUCTOS[id].codigo_item, id_producto: id, sucursal_id: sucursal, horizonte_dias: 15, rama,
  prediccion_q50: q50, intervalo_confianza: { limite_inferior: 0, limite_superior: limite, alpha_negocio: alpha },
  interpretacion, fecha_features: '2025-12-31', modelo_entrenado_en: '2026-09-25T01:30:56.264497+00:00',
})
const detalle = (stock, cobertura, semaforo) => ({
  stock_actual: stock, dias_cobertura: cobertura, semaforo,
  historial: [{ fecha: '2025-12-31', stock_disponible: stock, dias_cobertura: cobertura, semaforo }],
})

const PARES = {
  '91-1': {
    prediccion: prediccion(91, 'PRINCIPAL', 'intermitente', 3366.01, 4608.72, 0.893,
      'Demanda intermitente. Proyección: 3.366 unidades en 15 días hábiles. Cobertura recomendada: hasta 4.609 unidades.'),
    ventas: [2973, 2967, 3774, 2767, 2930, 2426, 3522, 4608],
    detalle: detalle(489, 2.9, 'critico'),
  },
  '91-3': {
    prediccion: prediccion(91, 'GLORIETA', 'suave_perecedero', 3871.25, 3094.03, 0.167,
      'Demanda estable, producto perecedero. Proyección: 3.871 unidades en 15 días hábiles.'),
    ventas: [3500, 3600, 3700, 3800, 3900, 3800, 3700, 4000],
    detalle: detalle(1200, 4.1, 'bajo'),
  },
  '171-1': {
    prediccion: prediccion(171, 'PRINCIPAL', 'suave_no_perecedero', 1251.25, 1659.64, 0.893,
      'Demanda estable. Proyección: 1.251 unidades en 15 días hábiles. Cobertura recomendada: hasta 1.660 unidades.'),
    ventas: [1200, 1300, 1250, 1100, 1280, 1310, 1190, 1260],
    detalle: detalle(556, 5.3, 'bajo'),
  },
  '321-1': {
    prediccion: prediccion(321, 'PRINCIPAL', 'intermitente', 135.68, 199.71, 0.893,
      'Demanda intermitente. Proyección: 135,7 kg en 15 días hábiles. Cobertura recomendada: hasta 199,7 kg.'),
    ventas: [141.48, 146.795, 182.3, 142.035, 128.36, 145.355, 131.15, 151.57],
    detalle: detalle(77.145, 6.3, 'bajo'),
  },
  '3367-1': {
    prediccion: { status: 404, body: { detail: 'No hay historia suficiente para producto_id=02458, sucursal_id=PRINCIPAL: '
      + '0 días con venta hasta 2025-12-31 (el modelo exige al menos 30)' } },
    ventas: [0, 0, 0, 0, 0, 0, 0, 0],
    detalle: detalle(38, 999, 'ok'),
  },
}

function rutas(cambios = {}) {
  const ventasDe = Object.keys(PRODUCTOS).map(id => [`GET /api/consulta/productos/${id}/ventas`, ({ params }) => ({
    body: { id_producto: Number(id), codigo_item: PRODUCTOS[id].codigo_item, unidad: PRODUCTOS[id].unidad,
      sucursal: params.sucursal_id === '3' ? 'GLORIETA' : 'PRINCIPAL', horizonte_dias_habiles: 15,
      fecha_fin: '2025-12-31', ventanas: ventanas(PARES[`${id}-${params.sucursal_id}`].ventas) },
  })])
  return {
    'GET /api/consulta/productos': ({ params }) => {
      const items = Object.values(PRODUCTOS).filter(p =>
        `${p.nombre} ${p.codigo_item}`.toLowerCase().includes(params.busqueda.toLowerCase()))
      return { body: { items, total: items.length, page: 1, page_size: 20, pages: 1 } }
    },
    'POST /api/ml/predict': ({ body }) => {
      const r = PARES[`${body.id_producto}-${body.id_sucursal}`].prediccion
      return r.status ? r : { body: r }
    },
    'GET /api/consulta/inventario/detalle': ({ params }) => ({
      body: PARES[`${params.id_producto}-${params.id_sucursal}`].detalle,
    }),
    ...Object.fromEntries(ventasDe),
    ...cambios,
  }
}

const buscador = () => screen.getByRole('searchbox', { name: 'Buscar producto' })

async function elegirProducto(texto, nombre) {
  await userEvent.clear(buscador())
  await userEvent.type(buscador(), texto)
  const lista = await screen.findByRole('list', { name: 'Productos encontrados' })
  await userEvent.click(within(lista).getByRole('button', { name: new RegExp(nombre.replace(/[*]/g, '\\*')) }))
}

async function elegirSucursal(id) {
  const select = screen.getByRole('combobox', { name: 'Sucursal' })
  await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(4))
  await userEvent.selectOptions(select, String(id))
}

const tarjeta = etiqueta => screen.getByText(etiqueta).closest('div')

describe('Predicciones (INV-26)', () => {
  it('pide producto y sucursal, sin "Todas las sucursales" ni la Bodega (V10)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Predicciones />)
    expect(screen.getByText(/Busque un producto por nombre o código y elija una sucursal/)).toBeInTheDocument()
    const select = screen.getByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(select).getAllByRole('option').map(o => o.textContent))
      .toEqual(['Elegir sucursal', 'PRINCIPAL', 'LA 21', 'GLORIETA']))
    expect(screen.getByText('Demanda prevista a 15 días hábiles')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /horizonte/i })).not.toBeInTheDocument()

    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    expect(screen.getByText('Elija una sucursal para ver el pronóstico del producto.')).toBeInTheDocument()
    expect(api.llamadas.some(l => l.ruta === '/api/ml/predict')).toBe(false)
  })

  it('busca 300 ms después de la última tecla, pide 20 y muestra nombre y código (V11)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await userEvent.type(buscador(), 'P1632')
    expect(api.llamadas.filter(l => l.ruta === '/api/consulta/productos')).toHaveLength(0)
    const lista = await screen.findByRole('list', { name: 'Productos encontrados' })
    expect(within(lista).getByRole('button')).toHaveTextContent('HUEVOS *UND · P1632 · Huevos')
    expect(api.llamadas.filter(l => l.ruta === '/api/consulta/productos').map(l => l.params))
      .toEqual([{ busqueda: 'P1632', page_size: '20' }])
  })

  it('avisa si no hay resultados o si hay más de los que muestra; Escape cierra la lista', async () => {
    simularApi(rutas({
      'GET /api/consulta/productos': ({ params }) => ({
        body: params.busqueda === 'ARROZ'
          ? { items: [PRODUCTOS[171]], total: 71, page: 1, page_size: 20, pages: 4 }
          : { items: [], total: 0, page: 1, page_size: 20, pages: 0 },
      }),
    }))
    renderConUsuario(<Predicciones />)
    await userEvent.type(buscador(), 'xyz')
    expect(await screen.findByText('Ningún producto coincide con «xyz».')).toBeInTheDocument()
    await userEvent.clear(buscador())
    await userEvent.type(buscador(), 'ARROZ')
    expect(await screen.findByText('Se muestran 1 de 71 productos: escriba más para acotar.')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(buscador()).toHaveValue('')
    expect(screen.queryByRole('list', { name: 'Productos encontrados' })).not.toBeInTheDocument()
  })

  it('HUEVOS *UND en PRINCIPAL: pronóstico, límite, riesgo urgente, stock, cobertura y fechas', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    await elegirSucursal(1)

    expect(await screen.findByText('3.366 unidades')).toBeInTheDocument()
    expect(tarjeta('Límite de negocio')).toHaveTextContent('4.609 unidades')
    expect(tarjeta('Límite de negocio')).toHaveTextContent('Cuantil de negocio (α = 0,893)')
    expect(screen.queryByText(/Cuantil bajo/)).not.toBeInTheDocument()
    expect(await screen.findByText('2,2 días hábiles')).toBeInTheDocument()
    expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('Urgente')
    expect(tarjeta('Stock actual')).toHaveTextContent('489 unidades')
    expect(tarjeta('Stock actual')).toHaveTextContent('Foto del 31 dic 2025')
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('2,9 d')
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('✕ Crítico')
    expect(screen.getByText(/Proyección: 3.366 unidades en 15 días hábiles/)).toBeInTheDocument()
    expect(screen.getByText(/Rama del modelo: Demanda intermitente/)).toBeInTheDocument()
    expect(screen.getByText('Features al 31 dic 2025 · Modelo entrenado el 25 sep 2026')).toBeInTheDocument()
    expect(screen.getByText(/La última ventana termina el 31 dic 2025 y el pronóstico la sigue\./)).toBeInTheDocument()
    expect(screen.getByText(/Cuantil de negocio \(α = 0,893\): 4.609 unidades/)).toBeInTheDocument()
    expect(screen.getByText('Stock actual: 489 unidades')).toBeInTheDocument()
    expect(screen.getByText(/Código P1632 · Huevos · Se vende por unidad · PRINCIPAL/)).toBeInTheDocument()

    expect(api.llamadas.find(l => l.ruta === '/api/ml/predict').body)
      .toEqual({ id_producto: 91, id_sucursal: 1, horizonte: 15 })
    expect(api.llamadas.find(l => l.ruta === '/api/consulta/productos/91/ventas').params)
      .toEqual({ sucursal_id: '1', ventanas: '8' })
    expect(api.llamadas.find(l => l.ruta === '/api/consulta/inventario/detalle').params)
      .toEqual({ id_producto: '91', id_sucursal: '1' })
  })

  it('ARROZ ZULIA en PRINCIPAL: las dos lecturas de riesgo se muestran por separado (V5)', async () => {
    simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await elegirProducto('P3937', 'ARROZ ZULIA')
    await elegirSucursal(1)
    expect(await screen.findByText('6,7 días hábiles')).toBeInTheDocument()
    expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('Alta')
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('5,3 d')
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('⚠ Bajo')
    expect(screen.getByText('Rama del modelo: Demanda estable', { exact: false })).toBeInTheDocument()
  })

  it('HUEVOS en GLORIETA, perecedero: el límite es un cuantil bajo (α = 0,167)', async () => {
    simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    await elegirSucursal(3)
    expect(await screen.findByText('3.094 unidades')).toBeInTheDocument()
    expect(tarjeta('Límite de negocio')).toHaveTextContent('Cuantil de negocio (α = 0,167)')
    expect(screen.getByText(/Cuantil bajo: queda bajo la mediana/)).toBeInTheDocument()
    expect(screen.getByText(/bajo la mediana: no es una cota de reposición/)).toBeInTheDocument()
    expect(screen.getByText(/Demanda estable, producto perecedero$/)).toBeInTheDocument()
  })

  it('PAPA PASTUSA, por kilo: demanda y stock en kg con decimales', async () => {
    simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await elegirProducto('PAPA', 'PAPA PASTUSA')
    await elegirSucursal(1)
    expect(await screen.findByText('135,7 kg')).toBeInTheDocument()
    expect(tarjeta('Límite de negocio')).toHaveTextContent('199,7 kg')
    expect(await screen.findByText('77,1 kg')).toBeInTheDocument()
    expect(screen.getByText(/Se vende por kilo \(kg\)/)).toBeInTheDocument()
  })

  it('historia insuficiente (404): el detail, con el stock y las ventanas en 0', async () => {
    simularApi(rutas())
    renderConUsuario(<Predicciones />)
    await elegirProducto('FRIJOL', 'FRIJOL CARGAMANTO')
    await elegirSucursal(1)
    const pronostico = screen.getByRole('region', { name: 'Pronóstico' })
    expect(await within(pronostico).findByRole('alert')).toHaveTextContent(
      'No hay historia suficiente para producto_id=02458, sucursal_id=PRINCIPAL')
    expect(within(pronostico).getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(await screen.findByText('38 unidades')).toBeInTheDocument()
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('Sin ventas')
    expect(screen.getByText(/El producto no vendió en PRINCIPAL entre el 2 sep 2025 y el 31 dic 2025/)).toBeInTheDocument()
    expect(screen.queryByText(/Features al/)).not.toBeInTheDocument()
    expect(screen.getByText(/La última ventana termina el 31 dic 2025\.$/)).toBeInTheDocument()
  })

  it('sin demanda prevista o con stock negativo, el riesgo no tiene días', async () => {
    const pares = { q50: 0, stock: 38 }
    simularApi(rutas({
      'POST /api/ml/predict': () => ({ body: { ...PARES['91-1'].prediccion, prediccion_q50: pares.q50 } }),
      'GET /api/consulta/inventario/detalle': () => ({ body: detalle(pares.stock, -347.4, 'inconsistencia') }),
    }))
    renderConUsuario(<Predicciones />)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    await elegirSucursal(1)
    await waitFor(() => expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('Sin demanda prevista'))
    expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('—')

    pares.q50 = 120
    pares.stock = -44
    await elegirSucursal(3)
    await waitFor(() => expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('Inconsistencia de inventario'))
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('—')
    expect(tarjeta('Cobertura del inventario')).toHaveTextContent('◆ Inconsistencia')
  })

  it('sin inventario en la sucursal (404 del detalle): el pronóstico se ve y el riesgo pide el stock', async () => {
    simularApi(rutas({
      'GET /api/consulta/inventario/detalle': { status: 404, body: { detail: 'No hay inventario para producto 91 en sucursal 1' } },
    }))
    renderConUsuario(<Predicciones />, USUARIOS.adminPrincipal)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    const inventario = screen.getByRole('region', { name: 'Inventario' })
    expect(await within(inventario).findByRole('alert')).toHaveTextContent('No hay inventario para producto 91 en sucursal 1')
    expect(tarjeta('Riesgo según el pronóstico')).toHaveTextContent('Necesita el stock de la foto de inventario')
    expect(screen.getByText('3.366 unidades')).toBeInTheDocument()
    expect(screen.queryByText(/Stock actual: /)).not.toBeInTheDocument()                 // sin línea de stock en la gráfica
  })

  it('mientras llega el stock, el riesgo lo espera', async () => {
    simularApi(rutas({
      'GET /api/consulta/inventario/detalle': { body: PARES['91-1'].detalle, demoraMs: 5000 },
    }))
    renderConUsuario(<Predicciones />, USUARIOS.adminPrincipal)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    expect(await screen.findByText('Esperando el stock de la foto…')).toBeInTheDocument()
  })

  it('un 503 del pronóstico se muestra con su texto y "Reintentar" vuelve a pedirlo', async () => {
    let intentos = 0
    const api = simularApi(rutas({
      'POST /api/ml/predict': () => (++intentos === 1 ? { status: 503, body: { detail: 'ml_service caído' } }
        : { body: PARES['91-1'].prediccion }),
    }))
    renderConUsuario(<Predicciones />)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    await elegirSucursal(1)
    expect(await screen.findByText('El servicio no está disponible en este momento.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('3.366 unidades')).toBeInTheDocument()
    expect(api.llamadas.filter(l => l.ruta === '/api/ml/predict')).toHaveLength(2)
  })

  it('admin_sucursal: sin selector, pronostica su sucursal', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Predicciones />, USUARIOS.adminPrincipal)
    expect(screen.getByText('Busque un producto por nombre o código para ver su pronóstico.')).toBeInTheDocument()
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    expect(await screen.findByText('3.366 unidades')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).not.toBeInTheDocument()
    expect(api.llamadas.find(l => l.ruta === '/api/ml/predict').body.id_sucursal).toBe(1)
  })

  it('al cambiar de producto antes de que responda el anterior, se cancela y se ignora la respuesta vieja', async () => {
    const api = simularApi(rutas({
      'POST /api/ml/predict': ({ body }) => (body.id_producto === 91
        ? { body: PARES['91-1'].prediccion, demoraMs: 5000 } : { body: PARES['171-1'].prediccion }),
    }))
    renderConUsuario(<Predicciones />, USUARIOS.adminPrincipal)
    await elegirProducto('HUEVOS', 'HUEVOS *UND')
    await elegirProducto('ARROZ', 'ARROZ ZULIA')
    expect(await screen.findByText('1.251 unidades')).toBeInTheDocument()
    const [, init] = api.fetch.mock.calls.find(([url, i]) => url.endsWith('/ml/predict') && i.body.includes('"id_producto":91'))
    expect(init.signal.aborted).toBe(true)
    expect(screen.queryByText('3.366 unidades')).not.toBeInTheDocument()
    expect(screen.getByText('ARROZ ZULIA *500 GR')).toBeInTheDocument()
  })
})
