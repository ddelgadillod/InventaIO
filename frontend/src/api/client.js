/**
 * InventAI/o — API Client
 * Handles auth tokens, refresh, and API calls.
 */

const BASE = '/api'

// ── Token storage ──────────────────────────────────
export function getTokens() {
  return {
    access: localStorage.getItem('access_token'),
    refresh: localStorage.getItem('refresh_token'),
  }
}

export function setTokens(access, refresh) {
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

export function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

// ── Core fetch wrapper ─────────────────────────────
async function apiFetch(path, options = {}) {
  const { access } = getTokens()
  const headers = { ...options.headers }

  if (access) {
    headers['Authorization'] = `Bearer ${access}`
  }
  if (options.body && typeof options.body === 'object') {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(options.body)
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  // Token expired → try refresh
  if (res.status === 401 && !options._retried) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      return apiFetch(path, { ...options, _retried: true })
    }
    clearTokens()
    window.location.href = '/login'
    throw new Error('Sesión expirada')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Error ${res.status}`)
  }

  return res.json()
}

async function tryRefresh() {
  const { refresh } = getTokens()
  if (!refresh) return false

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

// ── Auth endpoints ─────────────────────────────────
export async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Credenciales inválidas')
  }
  const data = await res.json()
  setTokens(data.access_token, data.refresh_token)
  return data
}

export async function logout() {
  const { refresh } = getTokens()
  try {
    await apiFetch('/auth/logout', {
      method: 'POST',
      body: { refresh_token: refresh },
    })
  } catch { /* ignore */ }
  clearTokens()
}

export async function getProfile() {
  return apiFetch('/auth/me')
}

// ── Data endpoints ─────────────────────────────────
export async function getKPIs(sucursalId) {
  const params = sucursalId ? `?sucursal_id=${sucursalId}` : ''
  return apiFetch(`/reportes/kpis${params}`)
}

export async function getInventarioResumen() {
  return apiFetch('/consulta/inventario/resumen')
}

export async function getAlertasResumen() {
  return apiFetch('/alertas/resumen')
}

export async function getAlertas(tipo, urgencia) {
  const params = new URLSearchParams()
  if (tipo) params.set('tipo', tipo)
  if (urgencia) params.set('urgencia', urgencia)
  const qs = params.toString() ? `?${params}` : ''
  return apiFetch(`/alertas${qs}`)
}

export async function getVentasTendencia(dias = 30) {
  return apiFetch(`/reportes/tendencias`)
}

export async function getTopProductos(limite = 5) {
  return apiFetch(`/reportes/ventas/top-productos?limite=${limite}`)
}

export async function getDistribucionCategorias() {
  return apiFetch('/reportes/distribucion-categorias')
}
