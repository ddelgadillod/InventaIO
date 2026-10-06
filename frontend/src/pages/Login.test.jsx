import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../api/AuthContext'
import Login from './Login'
import { simularApi, USUARIOS } from '../test/utils'

function abrirLogin() {
  const sesion = { user: null, loading: false, loginSuccess: vi.fn(), logout: vi.fn() }
  render(
    <AuthContext.Provider value={sesion}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<h2>Dashboard</h2>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return sesion
}

async function entrar(email, clave) {
  const usuario = userEvent.setup({ delay: null })
  await usuario.type(screen.getByLabelText('Correo electrónico'), email)
  await usuario.type(screen.getByLabelText('Contraseña'), clave)
  await usuario.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
}

describe('Login', () => {
  it('con la clave incorrecta muestra el mensaje y sigue en el login; los rótulos nombran sus campos', async () => {
    simularApi({ 'POST /api/auth/login': { status: 401, body: { detail: 'Credenciales inválidas' } } })
    abrirLogin()
    await entrar('gerente@inventaio.co', 'incorrecta')
    // role="alert": el lector de pantalla anuncia por qué no entró
    expect(await screen.findByRole('alert')).toHaveTextContent('Credenciales inválidas')
    expect(screen.queryByRole('heading', { name: 'Dashboard' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Correo electrónico')).toHaveValue('gerente@inventaio.co')
  })

  it('con la clave correcta guarda el perfil y entra al Dashboard', async () => {
    const api = simularApi({
      'POST /api/auth/login': { body: { access_token: 'a', refresh_token: 'r' } },
      'GET /api/auth/me': { body: USUARIOS.gerente },
    })
    const sesion = abrirLogin()
    await entrar('gerente@inventaio.co', 'admin123')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(sesion.loginSuccess).toHaveBeenCalledWith(USUARIOS.gerente)
    expect(api.llamadas[0].body).toEqual({ email: 'gerente@inventaio.co', password: 'admin123' })
  })

  it('con el Core API caído no culpa a las credenciales', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 502 })))
    abrirLogin()
    await entrar('gerente@inventaio.co', 'admin123')
    expect(await screen.findByRole('alert')).toHaveTextContent('Error 502')
    expect(screen.queryByText('Credenciales inválidas')).not.toBeInTheDocument()
  })

  it('con un correo que el navegador acepta y la API no, lo dice en español', async () => {
    simularApi({ 'POST /api/auth/login': { status: 422, body: { detail: [
      { loc: ['body', 'email'], msg: 'value is not a valid email address: The part after the @-sign is not valid.' }] } } })
    abrirLogin()
    await entrar('gerente@inventaio', 'admin123')
    expect(await screen.findByRole('alert')).toHaveTextContent('El correo electrónico no es válido')
  })
})
