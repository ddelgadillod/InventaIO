import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { getTokens, setTokens } from './client'
import { simularApi, USUARIOS } from '../test/utils'

function Sesion() {
  const { user, loading, logout } = useAuth()
  if (loading) return <p>cargando</p>
  return (
    <div>
      <p>{user ? user.nombre : 'sin sesión'}</p>
      <button onClick={logout}>salir</button>
    </div>
  )
}

describe('AuthContext', () => {
  it('con token carga el perfil de /auth/me', async () => {
    setTokens('a', 'r')
    simularApi({ 'GET /api/auth/me': { body: USUARIOS.adminPrincipal } })
    render(<AuthProvider><Sesion /></AuthProvider>)
    expect(await screen.findByText('Laura Gómez')).toBeInTheDocument()
  })

  it('sin token no consulta y queda sin sesión', async () => {
    const api = simularApi()
    render(<AuthProvider><Sesion /></AuthProvider>)
    expect(await screen.findByText('sin sesión')).toBeInTheDocument()
    expect(api.llamadas).toHaveLength(0)
  })

  it('si el perfil falla, borra los tokens', async () => {
    setTokens('a', 'r')
    simularApi({ 'GET /api/auth/me': { status: 500 } })
    render(<AuthProvider><Sesion /></AuthProvider>)
    expect(await screen.findByText('sin sesión')).toBeInTheDocument()
    expect(getTokens().access).toBeNull()
  })

  it('logout cierra la sesión', async () => {
    setTokens('a', 'r')
    simularApi({ 'GET /api/auth/me': { body: USUARIOS.gerente }, 'POST /api/auth/logout': { body: {} } })
    render(<AuthProvider><Sesion /></AuthProvider>)
    await userEvent.click(await screen.findByText('salir'))
    await waitFor(() => expect(screen.getByText('sin sesión')).toBeInTheDocument())
  })

  it('useAuth fuera del proveedor lanza un error', () => {
    // El error es el esperado: que no ensucie la salida de las pruebas
    const espia = vi.spyOn(console, 'error').mockImplementation(() => {})
    const silenciar = e => e.preventDefault()
    window.addEventListener('error', silenciar)
    expect(() => render(<Sesion />)).toThrow('useAuth must be inside AuthProvider')
    window.removeEventListener('error', silenciar)
    espia.mockRestore()
  })
})
