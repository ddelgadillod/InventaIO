/**
 * InventAI/o — Utilidades de prueba (INV-26 fix, A2.12)
 *
 *   renderConUsuario(<Pagina />, USUARIOS.adminPrincipal)
 *   const api = simularApi({ 'GET /api/alertas': { body: {...} } })
 *   api.llamadas  → [{ metodo, ruta, params, body }]
 *
 * Las respuestas de simularApi pueden ser { status, body, demoraMs } o una
 * función que recibe la llamada y devuelve ese objeto. Sin respuesta para una
 * ruta, responde 404; /api/consulta/sucursales ya viene simulada.
 */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { AuthContext } from '../api/AuthContext'

// Con la forma de /auth/me y los usuarios de prueba de la bodega real
export const USUARIOS = {
  gerente: { id: 1, email: 'gerente@inventaio.co', nombre: 'Carlos Martínez', rol: 'gerente',
    id_sucursal: null, sucursal_nombre: null, activo: true },
  adminPrincipal: { id: 2, email: 'admin.principal@inventaio.co', nombre: 'Laura Gómez', rol: 'admin_sucursal',
    id_sucursal: 1, sucursal_nombre: 'PRINCIPAL', activo: true },
  adminNorte: { id: 3, email: 'admin.norte@inventaio.co', nombre: 'Andrés Rivera', rol: 'admin_sucursal',
    id_sucursal: 2, sucursal_nombre: 'LA 21', activo: true },
  bodega: { id: 5, email: 'bodega@inventaio.co', nombre: 'Diego Sánchez', rol: 'admin_bodega',
    id_sucursal: 5, sucursal_nombre: 'BODEGA_CENTRAL', activo: true },
}

export const SUCURSALES = {
  items: [
    { id_sucursal: 1, codigo_tienda: 1, nombre: 'PRINCIPAL', tipo: 'principal' },
    { id_sucursal: 2, codigo_tienda: 2, nombre: 'LA 21', tipo: 'estandar' },
    { id_sucursal: 3, codigo_tienda: 3, nombre: 'GLORIETA', tipo: 'estandar' },
    { id_sucursal: 5, codigo_tienda: 5, nombre: 'BODEGA_CENTRAL', tipo: 'bodega_central' },
  ],
  total: 4,
}

export function renderConUsuario(ui, usuario = USUARIOS.gerente, { ruta = '/' } = {}) {
  const sesion = { user: usuario, loading: false, loginSuccess: vi.fn(), logout: vi.fn() }
  return render(
    <AuthContext.Provider value={sesion}>
      <MemoryRouter initialEntries={[ruta]}>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  )
}

function esperar(ms, signal) {
  return new Promise((resolve, reject) => {
    const cancelar = () => reject(new DOMException('Aborted', 'AbortError'))
    if (signal?.aborted) return cancelar()
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => { clearTimeout(t); cancelar() })
  })
}

export function simularApi(rutas = {}) {
  const llamadas = []
  const fetchFalso = vi.fn(async (url, init = {}) => {
    const metodo = (init.method || 'GET').toUpperCase()
    const u = new URL(url, 'http://localhost')
    const llamada = {
      metodo,
      ruta: u.pathname,
      params: Object.fromEntries(u.searchParams),
      body: init.body ? JSON.parse(init.body) : undefined,
      headers: init.headers || {},
    }
    llamadas.push(llamada)
    const clave = `${metodo} ${u.pathname}`
    let r = rutas[clave] ?? (clave === 'GET /api/consulta/sucursales' ? { body: SUCURSALES } : null)
    if (typeof r === 'function') r = r(llamada)
    if (!r) r = { status: 404, body: { detail: `Ruta no simulada: ${clave}` } }
    if (init.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (r.demoraMs) await esperar(r.demoraMs, init.signal)
    return new Response(JSON.stringify(r.body ?? {}), {
      status: r.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchFalso)
  return { llamadas, fetch: fetchFalso }
}
