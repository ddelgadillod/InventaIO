import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../api/AuthContext'
import { useSucursal } from './useSucursal'
import { simularApi, USUARIOS } from '../test/utils'

const conUsuario = usuario => ({ children }) => (
  <AuthContext.Provider value={{ user: usuario, loading: false }}>{children}</AuthContext.Provider>
)

describe('useSucursal (A2.6)', () => {
  it('el admin_sucursal queda fijo en su sucursal de /auth/me, con su nombre', () => {
    simularApi()
    const { result } = renderHook(() => useSucursal(), { wrapper: conUsuario(USUARIOS.adminNorte) })
    expect(result.current).toMatchObject({ sucursalId: 2, sucursalNombre: 'LA 21', showSelector: false, esBodega: false })
  })

  it('el gerente elige; el nombre y el tipo salen de la lista', async () => {
    simularApi()
    const { result } = renderHook(() => useSucursal(), { wrapper: conUsuario(USUARIOS.gerente) })
    expect(result.current).toMatchObject({ sucursalId: null, sucursalNombre: null, showSelector: true, esBodega: false })
    act(() => result.current.setSucursalId(5))
    await waitFor(() => expect(result.current.sucursalNombre).toBe('BODEGA_CENTRAL'))
    expect(result.current).toMatchObject({ sucursalId: 5, rawSucursalId: 5, esBodega: true })
    act(() => result.current.setSucursalId(3))
    expect(result.current).toMatchObject({ sucursalNombre: 'GLORIETA', esBodega: false })
  })

  it('el admin_bodega empieza viendo todas y tiene selector', () => {
    simularApi()
    const { result } = renderHook(() => useSucursal(), { wrapper: conUsuario(USUARIOS.bodega) })
    expect(result.current).toMatchObject({ sucursalId: null, showSelector: true })
  })

  it('un admin_sucursal sin sucursal en el perfil no envía ninguna', () => {
    simularApi()
    const usuario = { ...USUARIOS.adminNorte, id_sucursal: undefined, sucursal_nombre: undefined }
    const { result } = renderHook(() => useSucursal(), { wrapper: conUsuario(usuario) })
    expect(result.current).toMatchObject({ sucursalId: null, sucursalNombre: null })
  })
})
