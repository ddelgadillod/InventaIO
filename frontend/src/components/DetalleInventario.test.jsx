import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import DetalleInventario from './DetalleInventario'
import { renderConUsuario, simularApi, USUARIOS } from '../test/utils'

const DETALLE_ARROZ = {
  id_producto: 171, nombre_producto: 'ARROZ ZULIA *500 GR', categoria: 'Arroz', sucursal: 'PRINCIPAL', id_sucursal: 1,
  tipo_ubicacion: 'sucursal', stock_actual: 556, stock_bodega: 4024, stock_minimo: 300, stock_maximo: 1200,
  punto_reorden: 450, dias_cobertura: 5.3, semaforo: 'bajo',
  historial: [{ fecha: '2025-12-31', stock_disponible: 556, dias_cobertura: 5.3, semaforo: 'bajo' }],
}
// unidad_medida es la de la presentación (*500 GR) y no se usa: manda `unidad`
const PRODUCTO_ARROZ = {
  id_producto: 171, codigo_item: 'P3937', unidad_medida: 'g', unidad: 'unidad', proveedores: ['Distribuidora Valle S.A.S.'],
}

const valor = etiqueta => within(screen.getByText(etiqueta).parentElement).getByRole('definition').textContent

describe('DetalleInventario (A3.6)', () => {
  it('muestra stock, mínimos, cobertura, stock de la Bodega y proveedor', async () => {
    const api = simularApi({
      'GET /api/consulta/inventario/detalle': { body: DETALLE_ARROZ },
      'GET /api/consulta/productos/171': { body: PRODUCTO_ARROZ },
    })
    renderConUsuario(<DetalleInventario idProducto={171} idSucursal={1} onCerrar={() => {}} />, USUARIOS.adminPrincipal)
    expect(await screen.findByText('ARROZ ZULIA *500 GR')).toBeInTheDocument()
    expect(await screen.findByText('Distribuidora Valle S.A.S.')).toBeInTheDocument()
    expect(screen.getByText('Código P3937 · Se vende por unidad')).toBeInTheDocument()
    expect(valor('Stock actual')).toBe('556')
    expect(valor('Stock en la Bodega')).toBe('4.024')
    expect([valor('Stock mínimo'), valor('Stock máximo'), valor('Punto de reorden')]).toEqual(['300', '1.200', '450'])
    expect(valor('Cobertura')).toBe('5,3 d')
    expect(screen.getByText('⚠ Bajo')).toBeInTheDocument()
    expect(screen.getByText('31 dic 2025: 556')).toBeInTheDocument()
    expect(screen.getByText(/una sola foto de inventario/)).toBeInTheDocument()
    expect(api.llamadas[0].params).toEqual({ id_producto: '171', id_sucursal: '1' })
  })

  it('en una fila de la Bodega marca la ubicación y no repite su stock', async () => {
    simularApi({
      'GET /api/consulta/inventario/detalle': {
        body: { ...DETALLE_ARROZ, sucursal: 'BODEGA_CENTRAL', id_sucursal: 5, tipo_ubicacion: 'bodega_central',
          stock_actual: -12, stock_bodega: null, dias_cobertura: -3.1, semaforo: 'inconsistencia', historial: [] },
      },
      'GET /api/consulta/productos/171': { body: { ...PRODUCTO_ARROZ, proveedores: [] } },
    })
    renderConUsuario(<DetalleInventario idProducto={171} idSucursal={5} onCerrar={() => {}} />)
    expect(await screen.findByText('Bodega')).toBeInTheDocument()
    expect(valor('Stock en la Bodega')).toBe('—')
    expect(valor('Cobertura')).toBe('—')
    expect(screen.getByText('◆ Inconsistencia')).toBeInTheDocument()
    expect(await screen.findByText('Sin proveedor registrado')).toBeInTheDocument()
  })

  it('un producto por kilo lo dice en la descripción y lleva un decimal', async () => {
    simularApi({
      'GET /api/consulta/inventario/detalle': {
        body: { ...DETALLE_ARROZ, id_producto: 321, nombre_producto: 'PAPA PASTUSA *KL', stock_actual: 77.145,
          stock_bodega: 0, stock_minimo: 40.5, historial: [{ fecha: '2025-12-31', stock_disponible: 77.145 }] },
      },
      'GET /api/consulta/productos/321': {
        body: { id_producto: 321, codigo_item: 'P1814', unidad_medida: 'unidad', unidad: 'kg', proveedores: [] },
      },
    })
    renderConUsuario(<DetalleInventario idProducto={321} idSucursal={1} onCerrar={() => {}} />)
    expect(await screen.findByText('Código P1814 · Se vende por kilo (kg)')).toBeInTheDocument()
    expect([valor('Stock actual'), valor('Stock en la Bodega'), valor('Stock mínimo')]).toEqual(['77,1', '0,0', '40,5'])
    expect(screen.getByText('31 dic 2025: 77,1')).toBeInTheDocument()
  })

  it('muestra el error del Core API dentro del panel', async () => {
    simularApi({
      'GET /api/consulta/inventario/detalle': { status: 404, body: { detail: 'No hay inventario de ese producto en esa ubicación' } },
      'GET /api/consulta/productos/91': { status: 500 },
    })
    renderConUsuario(<DetalleInventario idProducto={91} idSucursal={5} onCerrar={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('No hay inventario de ese producto en esa ubicación')
  })

  it('el proveedor queda "No disponible" si su consulta falla', async () => {
    simularApi({
      'GET /api/consulta/inventario/detalle': { body: DETALLE_ARROZ },
      'GET /api/consulta/productos/171': { status: 500 },
    })
    renderConUsuario(<DetalleInventario idProducto={171} idSucursal={1} onCerrar={() => {}} />)
    expect(await screen.findByText('No disponible')).toBeInTheDocument()
    expect(valor('Stock actual')).toBe('556')
  })

  it('se cierra con el botón, con Escape y al hacer clic fuera', async () => {
    simularApi({ 'GET /api/consulta/inventario/detalle': { body: DETALLE_ARROZ }, 'GET /api/consulta/productos/171': { body: PRODUCTO_ARROZ } })
    const onCerrar = vi.fn()
    const { container } = renderConUsuario(<DetalleInventario idProducto={171} idSucursal={1} onCerrar={onCerrar} />)
    expect(container).toBeEmptyDOMElement()                   // se dibuja en un portal, en document.body
    await userEvent.click(screen.getByLabelText('Cerrar detalle'))
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('dialog'))          // dentro del panel: no cierra
    await userEvent.click(screen.getByRole('dialog').parentElement) // el fondo: cierra
    expect(onCerrar).toHaveBeenCalledTimes(3)
  })
})
