import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useSucursales } from './useSucursales'
import { simularApi } from '../test/utils'

function Nombres({ id }) {
  const { sucursales } = useSucursales()
  return <p data-testid={id}>{sucursales.map(s => s.nombre).join(',')}</p>
}

describe('useSucursales (A2.5)', () => {
  it('pide la lista una sola vez aunque la usen varios componentes', async () => {
    const api = simularApi()
    render(<><Nombres id="a" /><Nombres id="b" /><Nombres id="c" /></>)
    await waitFor(() => expect(screen.getByTestId('c')).toHaveTextContent('PRINCIPAL,LA 21,GLORIETA,BODEGA_CENTRAL'))
    expect(api.llamadas.filter(l => l.ruta === '/api/consulta/sucursales')).toHaveLength(1)
  })

  it('ofrece porId, porNombre y las sucursales físicas', async () => {
    simularApi()
    const { result } = renderHook(() => useSucursales())
    await waitFor(() => expect(result.current.cargando).toBe(false))
    expect(result.current.porId[5].nombre).toBe('BODEGA_CENTRAL')
    expect(result.current.porNombre['LA 21'].id_sucursal).toBe(2)
    expect(result.current.fisicas.map(s => s.nombre)).toEqual(['PRINCIPAL', 'LA 21', 'GLORIETA'])
  })

  it('si la carga falla expone el error y el siguiente uso la vuelve a pedir', async () => {
    const api = simularApi({ 'GET /api/consulta/sucursales': { status: 500 } })
    const primero = renderHook(() => useSucursales())
    await waitFor(() => expect(primero.result.current.error?.status).toBe(500))
    expect(primero.result.current.sucursales).toEqual([])
    renderHook(() => useSucursales())
    await waitFor(() => expect(api.llamadas).toHaveLength(2))
  })
})
