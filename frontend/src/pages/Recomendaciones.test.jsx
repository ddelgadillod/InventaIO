import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Recomendaciones from './Recomendaciones'
import { descargarCSV } from '../utils/csv'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

vi.mock('../utils/csv', async original => ({ ...(await original()), descargarCSV: vi.fn() }))

// Filas reales del Core API (INV-23) con la foto al 2025-12-31
const POLITICAS = { inv21: { version: 1, fecha: '2026-09-30' }, inv22: { version: 1, fecha: '2026-09-30' } }
const CALENDARIO = [
  { grupo: 'quincenal', tipo_destino: 'bodega_central', fecha_pedido: '2026-01-02', fecha_llegada: '2026-01-07',
    fecha_llegada_sucursal: '2026-01-09', pedido_siguiente: '2026-01-16', cubre_hasta: '2026-01-23', dias_cubiertos: 22,
    dias_hasta_llegada: 8 },
  { grupo: 'semanal', tipo_destino: 'sucursal', fecha_pedido: '2026-01-06', fecha_llegada: '2026-01-11',
    fecha_llegada_sucursal: '2026-01-11', pedido_siguiente: '2026-01-13', cubre_hasta: '2026-01-18', dias_cubiertos: 17,
    dias_hasta_llegada: 10 },
]
const AGUA = { producto_id: '00008', nombre_producto: 'AGUA CRISTAL LITRO SPORT', categoria: 'Bebidas', destino: 'BODEGA_CENTRAL',
  tipo_destino: 'bodega_central', grupo: 'quincenal', cantidad: 47, unidad: 'unidad', urgencia: 'normal', dias_hasta_agotarse: 10.5,
  fecha_pedido: '2026-01-02', fecha_llegada: '2026-01-07', fecha_llegada_sucursal: '2026-01-09', llega_tarde: false,
  necesidad: 46.86, necesidad_sucursal: 36.95, sobrante_bodega: 0, motivo: 'reposicion' }
const MINI_BON = { producto_id: '00087', nombre_producto: 'MINI BON YURT CHOCOCANDY ALPINA * 100', categoria: 'Lácteos',
  destino: 'PRINCIPAL', tipo_destino: 'sucursal', grupo: 'semanal', cantidad: 16, unidad: 'unidad', urgencia: 'urgente',
  dias_hasta_agotarse: 4.7, fecha_pedido: '2026-01-06', fecha_llegada: '2026-01-11', fecha_llegada_sucursal: '2026-01-11',
  llega_tarde: true, necesidad: 15.36, necesidad_sucursal: 15.36, sobrante_bodega: null, motivo: 'reposicion' }
const SANCOCHO = { ...MINI_BON, producto_id: '01621', nombre_producto: 'PAL SANCOCHO LA FAZENDA * 1.28 KL', categoria: 'Cárnicos',
  cantidad: 7, unidad: 'kg', dias_hasta_agotarse: 0, necesidad: 6.88, necesidad_sucursal: 6.88, motivo: 'stock_negativo' }
const LINEAS = [AGUA, MINI_BON, SANCOCHO]
const CUBRIR = [{ producto_id: '00022', nombre_producto: 'COLCAFE 3 EN 1 LIGHT *310GR', categoria: 'Café y sustitutos',
  necesidad: 2.82, necesidad_sucursal: 2.82, sobrante_bodega: 3, unidad: 'unidad', urgencia: 'urgente', dias_hasta_agotarse: 0 }]
const ALERTAS_COMPRAS = [
  { producto_id: '00195', nombre_producto: 'BRETAÑA *350 ML', categoria: 'Bebidas', sucursal: 'PRINCIPAL',
    tipo: 'posible_inconsistencia_inventario', stock: -1, accion: 'verificar_conteo', detalle: '…' },
  { producto_id: '00046', nombre_producto: 'SOFLAN SUAVITEL 2*970 ML', categoria: 'Aseo hogar', sucursal: 'BODEGA_CENTRAL',
    tipo: 'posible_inconsistencia_inventario', stock: -300, accion: 'compra_urgente', detalle: '…' },
]
const RESUMEN = {
  productos: 1411, lineas: 1340, lineas_sucursal: 449, lineas_bodega: 891, cantidad: { unidad: 41952, kg: 3169 },
  cantidad_directa: { unidad: 14854, kg: 3169 }, cantidad_bodega: { unidad: 27098, kg: 0 }, necesidad_via_bodega: null,
  cubiertos_por_bodega: 277, alertas: 220,
}
const RESUMEN_PRINCIPAL = { ...RESUMEN, lineas: 814, lineas_sucursal: 164, lineas_bodega: 650,
  necesidad_via_bodega: { unidad: 19637.39, kg: 0 } }

function compras({ sucursal = null, porRol = false, lineas = LINEAS, alertas = ALERTAS_COMPRAS, params = {} } = {}) {
  return {
    fecha_inventario: '2025-12-31', fecha_pronostico: '2025-12-31', lead_time_dias: 5, politicas: POLITICAS,
    calendario: CALENDARIO, compras: lineas, cubrir_con_traslado: CUBRIR, alertas, no_encontrados: [],
    resumen: sucursal && sucursal !== 'BODEGA_CENTRAL' ? RESUMEN_PRINCIPAL : RESUMEN,
    filtros_aplicados: { sucursal, sucursal_por_rol: porRol, categoria: params.categoria ?? null, urgencia: params.urgencia ?? null },
    calculado_en: '2026-10-06T19:57:08Z',
  }
}

const TRASLADOS = [
  { producto_id: '00380', nombre_producto: 'DURAZNO MARIA JOSE*  425 / 410 GR 24', categoria: 'Conservas', origen: 'BODEGA_CENTRAL',
    destino: 'PRINCIPAL', cantidad: 13, unidad: 'unidad', urgencia: 'urgente', dias_hasta_agotarse: 0, fecha_llegada: '2026-01-03',
    dias_habiles_llegada: 2, llega_tarde: true },
  { producto_id: '02104', nombre_producto: 'ATUN MI DIA LOMITOS AGUA * 140/160', categoria: 'Mariscos', origen: 'GLORIETA',
    destino: 'PRINCIPAL', cantidad: 6, unidad: 'unidad', urgencia: 'urgente', dias_hasta_agotarse: 3.7, fecha_llegada: '2026-01-03',
    dias_habiles_llegada: 2, llega_tarde: false },
]
const TRANSFERENCIAS = {
  fecha_inventario: '2025-12-31', fecha_pronostico: '2025-12-31', horizonte_dias: 15, politicas: { version: 1, fecha: '2026-09-30' },
  traslados: TRASLADOS, no_encontrados: [], calculado_en: '2026-10-06T19:57:28Z',
  alertas: [{ producto_id: '00008', nombre_producto: 'AGUA CRISTAL LITRO SPORT', categoria: 'Bebidas', sucursal: 'LA 21',
    tipo: 'stock_negativo', stock: -1, accion: 'pedido_urgente', detalle: '…' }],
  resumen: { productos: 4419, traslados: 119, cantidad_trasladada: { unidad: 4623, kg: 0 }, filas_balance: 11710,
    deficit_total: { unidad: 18772.5, kg: 1904.68 }, deficit_neto: { unidad: 14149.5, kg: 1904.68 },
    excedente_sin_destino: { unidad: 77064.69, kg: 17.29 }, alertas: 220, alertas_stock_negativo: 220, alertas_sin_pronostico: 2762 },
  filtros_aplicados: { sucursal: null, sucursal_por_rol: false, categoria: null, urgencia: null },
}

function rutas(cambios = {}) {
  return {
    'GET /api/ml/recomendaciones/compras': ({ params }) => ({ body: compras({ sucursal: params.sucursal ?? null, params }) }),
    'GET /api/ml/recomendaciones/transferencias': { body: TRANSFERENCIAS },
    'GET /api/consulta/categorias': { body: { items: [{ categoria: 'Lácteos' }, { categoria: 'Bebidas' }], total: 2 } },
    ...cambios,
  }
}

const llamadas = (api, tipo) => api.llamadas.filter(l => l.ruta === `/api/ml/recomendaciones/${tipo}`)
const tabla = nombre => screen.getByRole('region', { name: nombre })
const encabezados = nombre => within(tabla(nombre)).getAllByRole('columnheader').map(c => c.textContent)
const filas = nombre => within(tabla(nombre)).getAllByRole('row').slice(1)
const filaDe = (nombre, texto) => filas(nombre).find(f => f.textContent.includes(texto))

async function elegirSucursal(valor) {
  const select = screen.getByRole('combobox', { name: 'Sucursal' })
  await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(5))
  await userEvent.selectOptions(select, valor)
}

describe('Recomendaciones (INV-27)', () => {
  it('compras de toda la red: contexto, calendario, resumen y columnas, sin proveedor', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Recomendaciones />)
    expect(await screen.findByText('Calendario de pedidos')).toBeInTheDocument()
    expect(screen.getByText(/Toda la red · Foto de inventario del 31 dic 2025 · Calculado el 6 oct 2026 a las 19:57 UTC/))
      .toHaveTextContent('Políticas INV-21 v1 (30 sep 2026) e INV-22 v1 (30 sep 2026)')
    expect(screen.getByText('El proveedor entrega en 5 días.')).toBeInTheDocument()
    const calendario = screen.getByRole('heading', { name: 'Calendario de pedidos' }).parentElement
    const quincenal = within(calendario).getByRole('cell', { name: 'Quincenal (2 y 16)' }).closest('tr')
    expect([...quincenal.cells].map(c => c.textContent))
      .toEqual(['Quincenal (2 y 16)', 'Bodega', '2 ene 2026', '7 ene 2026', '9 ene 2026', '16 ene 2026', '23 ene 2026 (22 días)'])

    expect(screen.getByText('1.340')).toBeInTheDocument()
    expect(screen.getByText('449 a sucursales · 891 a la Bodega')).toBeInTheDocument()
    expect(screen.getByText('41.952 unidades')).toBeInTheDocument()
    expect(screen.getByText('3.169,0 kg')).toBeInTheDocument()
    expect(screen.queryByText('Necesidad vía la Bodega')).not.toBeInTheDocument()

    expect(encabezados('Compras a proveedor')).toEqual(['Producto', 'Destino', 'Grupo', 'Cantidad', 'Urgencia',
      'Días hasta agotarse', 'Pedido', 'Llega', 'Llega tarde', 'Motivo'])
    const agua = filaDe('Compras a proveedor', 'AGUA CRISTAL')
    expect(agua).toHaveTextContent('Bodega CentralBodega')
    expect(agua).toHaveTextContent('9 ene 2026a la Bodega: 7 ene 2026')
    expect(agua).toHaveTextContent('47 unidades')
    expect(filaDe('Compras a proveedor', 'MINI BON')).toHaveTextContent('Llega tarde')
    expect(filaDe('Compras a proveedor', 'SANCOCHO')).toHaveTextContent('7,0 kg')
    expect(filaDe('Compras a proveedor', 'SANCOCHO')).toHaveTextContent('Stock negativo')
    expect(screen.queryByText(/se calculan desde/)).not.toBeInTheDocument()

    expect(llamadas(api, 'compras').map(l => l.params)).toEqual([{ incluir_detalle: 'false' }])
    expect(llamadas(api, 'transferencias')).toHaveLength(0)
  })

  it('con la Bodega, la llamada lleva BODEGA_CENTRAL y no "Bodega Central" (V2)', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    await elegirSucursal('5')
    await waitFor(() => expect(llamadas(api, 'compras').at(-1).params.sucursal).toBe('BODEGA_CENTRAL'))
    expect(await screen.findByText(/^Bodega Central · Foto de inventario/)).toBeInTheDocument()
    expect(screen.queryByText(/se calculan desde/)).not.toBeInTheDocument()
    expect(encabezados('Compras a proveedor')).not.toContain('Necesidad de la sucursal')
  })

  it('sucursal, categoría y urgencia van en la llamada; desde una sucursal física, el aviso y la necesidad', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    await elegirSucursal('1')
    await waitFor(() => expect(screen.getByRole('option', { name: 'Lácteos' })).toBeInTheDocument())
    expect(within(screen.getByRole('combobox', { name: 'Categoría' })).getAllByRole('option').map(o => o.textContent))
      .toEqual(['Todas las categorías', 'Bebidas', 'Lácteos'])
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Categoría' }), 'Lácteos')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Urgencia' }), 'urgente')
    await waitFor(() => expect(llamadas(api, 'compras').at(-1).params)
      .toEqual({ sucursal: 'PRINCIPAL', categoria: 'Lácteos', urgencia: 'urgente', incluir_detalle: 'false' }))

    expect(await screen.findByText(
      'La urgencia y los días se calculan desde PRINCIPAL; la cantidad es la de toda la compra a la Bodega.')).toBeInTheDocument()
    expect(encabezados('Compras a proveedor').at(-1)).toBe('Necesidad de la sucursal')
    expect(filaDe('Compras a proveedor', 'AGUA CRISTAL')).toHaveTextContent('37 unidades')
    expect(screen.getByText('Necesidad vía la Bodega')).toBeInTheDocument()
    expect(screen.getByText('19.637 unidades')).toBeInTheDocument()
  })

  it('sin líneas de la Bodega no hay aviso aunque la sucursal sea física', async () => {
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': ({ params }) => ({ body: compras({ sucursal: params.sucursal ?? null, lineas: [MINI_BON] }) }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    await elegirSucursal('1')
    await screen.findByText('Necesidad vía la Bodega')
    expect(screen.queryByText(/se calculan desde/)).not.toBeInTheDocument()
  })

  it('cubrir con traslado y alertas, con el mismo rótulo para las dos inconsistencias', async () => {
    simularApi(rutas())
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    // Necesidad 2,82 y sobrante 3: en unidades, las dos se ven "3 unidades"
    expect(filaDe('Cubrir con traslado desde la Bodega', 'COLCAFE')).toHaveTextContent('3 unidades3 unidadesUrgente0,0')
    const bretana = filaDe('Alertas de inventario', 'BRETAÑA')
    expect(bretana).toHaveTextContent('Inconsistencia de inventario')
    expect(bretana).toHaveTextContent('Verificar el conteo')
    const soflan = filaDe('Alertas de inventario', 'SOFLAN')
    expect(soflan).toHaveTextContent('Bodega CentralBodega')
    expect(soflan).toHaveTextContent('-300')
    expect(soflan).toHaveTextContent('Compra urgente')

    await userEvent.click(screen.getByRole('tab', { name: 'Transferencias' }))
    const agua = await waitFor(() => filaDe('Alertas de inventario', 'AGUA CRISTAL'))
    expect(agua).toHaveTextContent('Inconsistencia de inventario')
    expect(agua).toHaveTextContent('Pedido urgente')
    expect(screen.getByText(/Además hay 2.762 pares sin pronóstico \(acción: ninguna\)/)).toBeInTheDocument()
  })

  it('transferencias: origen, destino, cantidad, urgencia, llegada y llega tarde; vigilancia solo aquí', async () => {
    const api = simularApi(rutas())
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    const urgencia = screen.getByRole('combobox', { name: 'Urgencia' })
    expect(within(urgencia).queryByRole('option', { name: 'Vigilancia' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Transferencias' }))
    expect(await screen.findByText('Cantidad trasladada')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Transferencias' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Políticas INV-22 v1 \(30 sep 2026\)/)).toBeInTheDocument()
    expect(screen.getByText('4.623 unidades')).toBeInTheDocument()
    expect(screen.getByText('14.150 unidades')).toBeInTheDocument()
    expect(screen.getByText('1.904,7 kg')).toBeInTheDocument()
    expect(encabezados('Traslados')).toEqual(['Producto', 'Origen', 'Destino', 'Cantidad', 'Urgencia', 'Días hasta agotarse',
      'Llega', 'Llega tarde'])
    const durazno = filaDe('Traslados', 'DURAZNO')
    expect(durazno).toHaveTextContent('Bodega CentralBodegaPRINCIPAL13 unidadesUrgente0,03 ene 2026en 2 días hábilesLlega tarde')
    expect(filaDe('Traslados', 'ATUN')).toHaveTextContent('GLORIETAPRINCIPAL6 unidades')
    expect(filaDe('Traslados', 'ATUN')).not.toHaveTextContent('Llega tarde')

    await userEvent.selectOptions(urgencia, 'vigilancia')
    await waitFor(() => expect(llamadas(api, 'transferencias').at(-1).params)
      .toEqual({ urgencia: 'vigilancia', incluir_balance: 'false' }))
    await userEvent.click(screen.getByRole('tab', { name: 'Compras' }))
    expect(urgencia).toHaveValue('')
    await waitFor(() => expect(llamadas(api, 'compras').at(-1).params).toEqual({ incluir_detalle: 'false' }))
  })

  it('búsqueda local por nombre o código, sin tildes, y paginación de a 50', async () => {
    const muchas = Array.from({ length: 120 }, (_, i) => ({ ...MINI_BON, producto_id: String(1000 + i), nombre_producto: `PRODUCTO ${i}` }))
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => ({ body: compras({ lineas: [AGUA, ...muchas] }) }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    const compra = tabla('Compras a proveedor')
    expect(within(compra).getByText('Página 1 de 3 · 121 líneas')).toBeInTheDocument()
    expect(filas('Compras a proveedor')).toHaveLength(50)
    await userEvent.click(within(compra).getByRole('button', { name: 'Página siguiente' }))
    expect(within(compra).getByText('Página 2 de 3 · 121 líneas')).toBeInTheDocument()

    await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar producto' }), 'agúa')
    expect(filas('Compras a proveedor')).toHaveLength(1)
    expect(within(tabla('Compras a proveedor')).getByText('1 línea')).toBeInTheDocument()
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Buscar producto' }))
    await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar producto' }), '1005')
    expect(filas('Compras a proveedor').map(f => f.cells[0].textContent)).toEqual(['PRODUCTO 51005 · Lácteos'])
  })

  it('la exportación lleva todas las filas filtradas, con el formato de V12', async () => {
    const muchas = Array.from({ length: 60 }, (_, i) => ({ ...MINI_BON, producto_id: String(2000 + i), nombre_producto: `YOGURT ${i}` }))
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => ({ body: compras({ lineas: [AGUA, SANCOCHO, ...muchas] }) }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar producto' }), 'yogurt')
    await userEvent.click(within(tabla('Compras a proveedor')).getByRole('button', { name: 'Exportar CSV' }))
    const [nombre, texto] = descargarCSV.mock.calls.at(-1)
    expect(nombre).toBe('recomendaciones-compras-2025-12-31.csv')
    const lineas = texto.slice(1).trimEnd().split('\r\n')
    expect(texto.charCodeAt(0)).toBe(0xFEFF)
    expect(lineas[0]).toBe('Código;Producto;Categoría;Destino;Grupo;Cantidad;Unidad;Urgencia;Días hasta agotarse (hábiles);'
      + 'Pedido;Llega a la sucursal;Llega a la Bodega;Llega tarde;Motivo;Foto de inventario;Calculado en')
    expect(lineas).toHaveLength(61)
    expect(lineas[1]).toBe('2000;YOGURT 0;Lácteos;PRINCIPAL;Semanal (martes);16;unidad;Urgente;4,7;2026-01-06;2026-01-11;;sí;'
      + 'Reposición;2025-12-31;2026-10-06T19:57:08Z')

    await userEvent.clear(screen.getByRole('searchbox', { name: 'Buscar producto' }))
    await userEvent.click(within(tabla('Compras a proveedor')).getByRole('button', { name: 'Exportar CSV' }))
    const todas = descargarCSV.mock.calls.at(-1)[1].trimEnd().split('\r\n')
    expect(todas).toHaveLength(63)
    expect(todas[1]).toContain(';Bodega Central;Quincenal (2 y 16);47;unidad;Normal;10,5;2026-01-02;2026-01-09;2026-01-07;no;')
    expect(todas[2]).toContain(';7;kg;')
  })

  it('exportar desde una sucursal: su nombre en el archivo y la necesidad de la sucursal; también los traslados', async () => {
    simularApi(rutas({
      'GET /api/ml/recomendaciones/transferencias': ({ params }) => ({
        body: { ...TRANSFERENCIAS, filtros_aplicados: { ...TRANSFERENCIAS.filtros_aplicados, sucursal: params.sucursal ?? null } },
      }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    await elegirSucursal('2')
    await screen.findByText(/se calculan desde LA 21/)
    await userEvent.click(within(tabla('Compras a proveedor')).getByRole('button', { name: 'Exportar CSV' }))
    let [nombre, texto] = descargarCSV.mock.calls.at(-1)
    expect(nombre).toBe('recomendaciones-compras-LA_21-2025-12-31.csv')
    expect(texto.split('\r\n')[0]).toContain(';Motivo;Necesidad de la sucursal;Foto de inventario;')
    expect(texto.split('\r\n')[1]).toContain(';Reposición;36,95;2025-12-31;')

    await userEvent.click(screen.getByRole('tab', { name: 'Transferencias' }))
    await userEvent.click(await within(await screen.findByRole('region', { name: 'Traslados' }))
      .findByRole('button', { name: 'Exportar CSV' }))
    ;[nombre, texto] = descargarCSV.mock.calls.at(-1)
    expect(nombre).toBe('recomendaciones-transferencias-LA_21-2025-12-31.csv')
    const lineas = texto.slice(1).trimEnd().split('\r\n')
    expect(lineas[0]).toBe('Código;Producto;Categoría;Origen;Destino;Cantidad;Unidad;Urgencia;Días hasta agotarse (hábiles);'
      + 'Llega;Días hábiles hasta la llegada;Llega tarde;Foto de inventario;Calculado en')
    expect(lineas[1]).toBe('00380;DURAZNO MARIA JOSE*  425 / 410 GR 24;Conservas;Bodega Central;PRINCIPAL;13;unidad;Urgente;0;'
      + '2026-01-03;2;sí;2025-12-31;2026-10-06T19:57:28Z')
  })

  it('las páginas avanzan y retroceden', async () => {
    const muchas = Array.from({ length: 60 }, (_, i) => ({ ...MINI_BON, producto_id: String(3000 + i) }))
    simularApi(rutas({ 'GET /api/ml/recomendaciones/compras': () => ({ body: compras({ lineas: muchas }) }) }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    const compra = tabla('Compras a proveedor')
    expect(within(compra).getByRole('button', { name: 'Página anterior' })).toBeDisabled()
    await userEvent.click(within(compra).getByRole('button', { name: 'Página siguiente' }))
    expect(within(compra).getByRole('button', { name: 'Página siguiente' })).toBeDisabled()
    expect(filas('Compras a proveedor')).toHaveLength(10)
    await userEvent.click(within(compra).getByRole('button', { name: 'Página anterior' }))
    expect(within(compra).getByText('Página 1 de 2 · 60 líneas')).toBeInTheDocument()
  })

  it('una lista vacía dice "Sin resultados", sin botón de exportar', async () => {
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => ({ body: compras({ lineas: [], alertas: [] }) }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    expect(within(tabla('Compras a proveedor')).getByText('Sin resultados para estos filtros.')).toBeInTheDocument()
    expect(within(tabla('Compras a proveedor')).queryByRole('button', { name: 'Exportar CSV' })).not.toBeInTheDocument()
  })

  it('valores sin etiqueta no rompen la página', async () => {
    const rara = { ...MINI_BON, urgencia: 'urgencia_nueva', motivo: 'motivo_nuevo', grupo: 'mensual' }
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => ({
        body: compras({ lineas: [rara], alertas: [{ ...ALERTAS_COMPRAS[0], tipo: 'tipo_nuevo', accion: 'accion_nueva' }] }),
      }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    const fila = filaDe('Compras a proveedor', 'MINI BON')
    expect([...fila.cells].map(c => c.textContent)).toEqual(expect.arrayContaining(['mensual', 'urgencia nueva', 'motivo nuevo']))
    expect(filaDe('Alertas de inventario', 'BRETAÑA')).toHaveTextContent('tipo nuevoaccion nueva')
  })

  it('al cambiar un filtro rápido se cancela la consulta anterior', async () => {
    const api = simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': ({ params }) => ({
        body: compras({ sucursal: params.sucursal ?? null, params }), demoraMs: params.urgencia === 'alta' ? 5000 : 0,
      }),
    }))
    renderConUsuario(<Recomendaciones />)
    await screen.findByText('Calendario de pedidos')
    const urgencia = screen.getByRole('combobox', { name: 'Urgencia' })
    await userEvent.selectOptions(urgencia, 'alta')
    await userEvent.selectOptions(urgencia, 'normal')
    expect(await screen.findByText('Calendario de pedidos')).toBeInTheDocument()
    const alta = api.fetch.mock.calls.find(([url]) => url.includes('urgencia=alta'))
    expect(alta[1].signal.aborted).toBe(true)
    expect(llamadas(api, 'compras').at(-1).params.urgencia).toBe('normal')
  })

  it.each([
    [409, 'La foto de inventario (2026-01-15) es posterior a la última venta cargada (2025-12-31).',
      'La foto de inventario (2026-01-15) es posterior a la última venta cargada (2025-12-31).'],
    [503, 'ml_service no disponible', 'El servicio no está disponible en este momento.'],
    [504, 'ml_service no respondió', 'El servicio no respondió a tiempo. Intente de nuevo en unos minutos.'],
  ])('un %i muestra su mensaje con "Reintentar"', async (status, detail, texto) => {
    let intentos = 0
    simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => (++intentos === 1 ? { status, body: { detail } } : { body: compras() }),
    }))
    renderConUsuario(<Recomendaciones />)
    expect(await screen.findByRole('alert')).toHaveTextContent(texto)
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Calendario de pedidos')).toBeInTheDocument()
  })

  it('admin_sucursal: sin selector; la API le aplica su sucursal', async () => {
    const api = simularApi(rutas({
      'GET /api/ml/recomendaciones/compras': () => ({ body: compras({ sucursal: 'PRINCIPAL', porRol: true }) }),
    }))
    renderConUsuario(<Recomendaciones />, USUARIOS.adminPrincipal)
    expect(await screen.findByText(/^PRINCIPAL · Foto de inventario/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).not.toBeInTheDocument()
    expect(llamadas(api, 'compras')[0].params).toEqual({ incluir_detalle: 'false' })
    expect(await screen.findByText(/se calculan desde PRINCIPAL/)).toBeInTheDocument()
  })

  it('admin_bodega elige como el gerente, también la Bodega', async () => {
    simularApi(rutas())
    renderConUsuario(<Recomendaciones />, USUARIOS.bodega)
    await screen.findByText('Calendario de pedidos')
    const select = screen.getByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(within(select).getAllByRole('option').map(o => o.textContent))
      .toEqual(['Todas las sucursales', 'PRINCIPAL', 'LA 21', 'GLORIETA', 'Bodega Central']))
  })
})
