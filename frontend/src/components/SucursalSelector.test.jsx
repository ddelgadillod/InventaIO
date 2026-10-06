import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SucursalSelector from './SucursalSelector'
import { simularApi } from '../test/utils'

const opciones = () => screen.getAllByRole('option').map(o => o.textContent)

describe('SucursalSelector (A2.7)', () => {
  it('lista las ubicaciones con la Bodega como "Bodega Central"', async () => {
    simularApi()
    render(<SucursalSelector value={null} onChange={() => {}} />)
    await waitFor(() => expect(opciones()).toEqual(['Todas las sucursales', 'PRINCIPAL', 'LA 21', 'GLORIETA', 'Bodega Central']))
  })

  it('con incluirBodega={false} no lista la Bodega', async () => {
    simularApi()
    render(<SucursalSelector value={null} onChange={() => {}} incluirBodega={false} />)
    await waitFor(() => expect(opciones()).toEqual(['Todas las sucursales', 'PRINCIPAL', 'LA 21', 'GLORIETA']))
  })

  it('entrega el id como número, o null para todas', async () => {
    simularApi()
    const onChange = vi.fn()
    render(<SucursalSelector value={3} onChange={onChange} />)
    const select = await screen.findByRole('combobox', { name: 'Sucursal' })
    await waitFor(() => expect(opciones()).toHaveLength(5))
    await userEvent.selectOptions(select, '5')
    await userEvent.selectOptions(select, '')
    expect(onChange.mock.calls).toEqual([[5], [null]])
  })

  it('avisa si la carga falla', async () => {
    simularApi({ 'GET /api/consulta/sucursales': { status: 500 } })
    render(<SucursalSelector value={null} onChange={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron cargar las sucursales')
  })
})
