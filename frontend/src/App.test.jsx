import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { setTokens } from './api/client'
import { simularApi, USUARIOS } from './test/utils'
// Las vistas se cargan con lazy (A11); importarlas antes evita que la prueba
// dependa de lo que tarda la primera carga de recharts con la suite en paralelo
import './pages/Dashboard'
import './pages/Alertas'

function abrir(usuario, ruta) {
  setTokens('a', 'r')
  simularApi({ 'GET /api/auth/me': { body: usuario } })
  return render(<MemoryRouter initialEntries={[ruta]}><App /></MemoryRouter>)
}

const menu = () => within(screen.getByRole('navigation')).getAllByRole('button').map(b => b.textContent)

describe('App con la sesión real', () => {
  it('el menú sale de RUTAS y el admin_bodega entra al Dashboard (A2.9, H2)', async () => {
    abrir(USUARIOS.bodega, '/')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(menu()).toEqual(['Dashboard', 'Inventario', 'Alertas', 'Reportes'])
    // En pantallas angostas el menú se abre y se cierra con estos botones de solo ícono
    expect(screen.getByRole('button', { name: 'Abrir menú' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar menú' })).toBeInTheDocument()
  })

  it('en pantallas angostas el menú cerrado no recibe el foco y "Abrir menú" dice si está abierto', async () => {
    vi.stubGlobal('matchMedia', media => ({ matches: false, media, addEventListener() {}, removeEventListener() {} }))
    abrir(USUARIOS.gerente, '/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard' })
    const menuLateral = document.getElementById('menu-lateral')
    const abrirMenu = screen.getByRole('button', { name: 'Abrir menú' })
    expect(menuLateral).toHaveAttribute('inert')
    expect(abrirMenu).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(abrirMenu)
    expect(menuLateral).not.toHaveAttribute('inert')
    expect(abrirMenu).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(within(menuLateral).getByRole('button', { name: 'Cerrar menú' }))
    expect(menuLateral).toHaveAttribute('inert')
  })

  it('una ruta desconocida vuelve al inicio del rol', async () => {
    abrir(USUARIOS.adminPrincipal, '/no-existe')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getAllByText('PRINCIPAL').length).toBeGreaterThan(0)
  })

  it('el menú navega y abre el cambio de contraseña (A3.7)', async () => {
    abrir(USUARIOS.gerente, '/dashboard')
    await userEvent.click(await screen.findByRole('button', { name: 'Alertas' }))
    expect(await screen.findByRole('heading', { name: 'Alertas' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))
    expect(screen.getByRole('dialog', { name: 'Cambiar contraseña' })).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Cerrar'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('sin sesión manda al login', async () => {
    simularApi()
    render(<MemoryRouter initialEntries={['/inventario']}><App /></MemoryRouter>)
    expect(await screen.findByPlaceholderText('tucorreo@inventaio.co')).toBeInTheDocument()
  })
})
