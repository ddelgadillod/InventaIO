import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { setTokens } from './api/client'
import { simularApi, textoSSE, USUARIOS } from './test/utils'
import { FLUJO_ALERTAS } from './test/vera'
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
    expect(menu()).toEqual(['Dashboard', 'Inventario', 'Alertas', 'Reportes', 'Predicciones', 'Recomendaciones'])
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

  it('Vera está para los 3 roles y su conversación sigue al cambiar de ruta (INV-35, CA 1)', async () => {
    abrir(USUARIOS.adminPrincipal, '/dashboard')
    simularApi({
      'GET /api/auth/me': { body: USUARIOS.adminPrincipal },
      'POST /api/chat/message': { sse: textoSSE(FLUJO_ALERTAS) },
    })
    await screen.findByRole('heading', { name: 'Dashboard' })
    await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
    const campo = await screen.findByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
    await userEvent.type(campo, '¿Alertas?{Enter}')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    await userEvent.click(screen.getByRole('button', { name: 'Alertas' }))
    expect(await screen.findByRole('heading', { name: 'Alertas' })).toBeInTheDocument()
    expect(screen.getByText('¿Alertas?')).toBeInTheDocument()
    // Cerrar y volver a abrir tampoco la pierde
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar el chat' }))
    await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
    expect(await screen.findByText('¿Alertas?')).toBeInTheDocument()
  })

  it('en móvil Vera ocupa la pantalla: lo de atrás no recibe el foco hasta cerrarla', async () => {
    vi.stubGlobal('matchMedia', media => ({ matches: false, media, addEventListener() {}, removeEventListener() {} }))
    abrir(USUARIOS.gerente, '/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard' })
    const principal = screen.getByRole('main').parentElement
    expect(principal).not.toHaveAttribute('inert')
    await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
    await screen.findByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
    expect(principal).toHaveAttribute('inert')
    expect(document.getElementById('menu-lateral')).toHaveAttribute('inert')
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar el chat' }))
    expect(principal).not.toHaveAttribute('inert')
  })

  it('en pantalla ancha Vera flota sin bloquear la página; maximizada, sí', async () => {
    abrir(USUARIOS.gerente, '/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard' })
    const principal = screen.getByRole('main').parentElement
    await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
    await screen.findByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
    expect(principal).not.toHaveAttribute('inert')
    // La ventana es fija: no ocupa lugar entre las columnas ni angosta la página
    expect(screen.getByRole('dialog', { name: 'Chat con Vera' })).toHaveClass('fixed')
    await userEvent.click(screen.getByRole('button', { name: 'Maximizar' }))
    expect(principal).toHaveAttribute('inert')
    await userEvent.click(screen.getByRole('button', { name: 'Restaurar el tamaño' }))
    expect(principal).not.toHaveAttribute('inert')
  })

  it('el primer Tab ofrece «Saltar al contenido» y lleva el foco a la página (M13 de INV-35)', async () => {
    abrir(USUARIOS.gerente, '/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard' })
    await userEvent.tab()
    const saltar = screen.getByRole('link', { name: 'Saltar al contenido' })
    expect(saltar).toHaveFocus()
    await userEvent.click(saltar)
    expect(screen.getByRole('main')).toHaveFocus()
  })

  it('el título de la pestaña sigue la página (M6 de INV-35)', async () => {
    abrir(USUARIOS.gerente, '/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(document.title).toBe('Dashboard · InventAI/o')
    await userEvent.click(screen.getByRole('button', { name: 'Alertas' }))
    await screen.findByRole('heading', { name: 'Alertas' })
    expect(document.title).toBe('Alertas · InventAI/o')
  })

  it('sin sesión manda al login', async () => {
    simularApi()
    render(<MemoryRouter initialEntries={['/inventario']}><App /></MemoryRouter>)
    expect(await screen.findByPlaceholderText('tucorreo@inventaio.co')).toBeInTheDocument()
    expect(document.title).toBe('Iniciar sesión · InventAI/o')
  })
})
