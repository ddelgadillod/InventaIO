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

// ── Helpers ────────────────────────────────────────
function buildQS(params) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') qs.set(k, v)
  })
  const s = qs.toString()
  return s ? `?${s}` : ''
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

// ── Catálogos ──────────────────────────────────────
export async function getSucursales() {
  return apiFetch('/consulta/sucursales')
}

// ── Dashboard / Reportes ───────────────────────────
export async function getKPIs(sucursalId = null) {
  return apiFetch(`/reportes/kpis${buildQS({ sucursal_id: sucursalId })}`)
}

export async function getVentasTendencia(dias = 30, sucursalId = null) {
  return apiFetch(`/reportes/tendencias${buildQS({ dias, sucursal_id: sucursalId })}`)
}

export async function getTopProductos(limite = 5, sucursalId = null) {
  return apiFetch(`/reportes/ventas/top-productos${buildQS({ limite, sucursal_id: sucursalId })}`)
}

export async function getDistribucionCategorias(sucursalId = null) {
  return apiFetch(`/reportes/distribucion-categorias${buildQS({ sucursal_id: sucursalId })}`)
}

// ── Inventario ─────────────────────────────────────
export async function getInventarioResumen(sucursalId = null) {
  return apiFetch(`/consulta/inventario/resumen${buildQS({ sucursal_id: sucursalId })}`)
}

export async function getInventario(params = {}) {
  return apiFetch(`/consulta/inventario${buildQS(params)}`)
}

// ── Alertas ────────────────────────────────────────
export async function getAlertasResumen(sucursalId = null) {
  return apiFetch(`/alertas/resumen${buildQS({ sucursal_id: sucursalId })}`)
}

export async function getAlertas(tipo, urgencia, sucursalId = null) {
  return apiFetch(`/alertas${buildQS({ tipo, urgencia, sucursal_id: sucursalId })}`)
}
