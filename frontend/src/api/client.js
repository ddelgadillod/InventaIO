/**
 * InventAI/o — Cliente del Core API
 * Tokens, refresh, errores con código HTTP (ApiError), timeout y cancelación
 * (INV-26 fix, A2.1–A2.3). Cada función tiene su consumidor en la matriz de
 * frontend/README.md: no se agregan funciones sin una pantalla que las use.
 *
 * Todas aceptan como último argumento las opciones de la consulta:
 *   signal    cancela la petición (lo usa useConsulta)
 *   timeoutMs la corta al vencer y lanza ApiError con `timeout`
 *   clave     una petición nueva con la misma clave cancela la anterior
 */

const BASE = '/api'

// Más que los 120 s del Core API hacia ml_service, para recibir su 504 (G4)
export const TIMEOUT_ML_MS = 130_000

export class ApiError extends Error {
  constructor(status, detail, { cancelada = false, timeout = false } = {}) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.cancelada = cancelada
    this.timeout = timeout
  }
}

// El detail de un 422 de validación es una lista: se convierte en texto
export function textoDetalle(detail, status) {
  if (Array.isArray(detail)) {
    return detail
      .map(e => {
        const campo = (e.loc || []).filter(p => !['body', 'query', 'path'].includes(p)).join('.')
        return campo ? `${campo}: ${e.msg}` : e.msg
      })
      .join('; ')
  }
  if (typeof detail === 'string' && detail) return detail
  return `Error ${status}`
}

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
const enCurso = new Map() // clave → AbortController de la petición vigente

async function apiFetch(path, opciones = {}) {
  const { timeoutMs, clave, signal, _reintento, ...init } = opciones
  const controller = new AbortController()
  if (clave) {
    enCurso.get(clave)?.abort()
    enCurso.set(clave, controller)
  }
  const alCancelar = () => controller.abort()
  if (signal?.aborted) controller.abort()
  signal?.addEventListener('abort', alCancelar)
  let vencio = false
  const timer = timeoutMs
    ? setTimeout(() => { vencio = true; controller.abort() }, timeoutMs)
    : null

  const { access } = getTokens()
  const headers = { ...init.headers }
  if (access) headers.Authorization = `Bearer ${access}`
  let body = init.body
  if (body && typeof body === 'object') {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }

  let res, datos
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers, body, signal: controller.signal })
    if (res.status !== 401) datos = await res.json().catch(() => ({}))
  } catch {
    if (vencio) {
      throw new ApiError(0, `La consulta tardó más de ${Math.round(timeoutMs / 1000)} s`, { timeout: true })
    }
    if (controller.signal.aborted) throw new ApiError(0, 'Consulta cancelada', { cancelada: true })
    throw new ApiError(0, 'No hay conexión con el servidor')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', alCancelar)
    if (clave && enCurso.get(clave) === controller) enCurso.delete(clave)
  }

  // Token vencido → se intenta renovar una vez
  if (res.status === 401) {
    if (!_reintento && (await tryRefresh())) {
      return apiFetch(path, { ...opciones, _reintento: true })
    }
    clearTokens()
    window.location.href = '/login'
    throw new ApiError(401, 'Sesión expirada')
  }

  if (!res.ok) throw new ApiError(res.status, textoDetalle(datos?.detail, res.status))
  return datos
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

const conTimeoutML = (op = {}) => ({ timeoutMs: TIMEOUT_ML_MS, ...op })

// ── Auth ───────────────────────────────────────────
export async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new ApiError(res.status, err.detail ? textoDetalle(err.detail, res.status) : 'Credenciales inválidas')
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
  } catch { /* la sesión se cierra igual */ }
  clearTokens()
}

export function getProfile(op) {
  return apiFetch('/auth/me', op)
}

export function cambiarPassword(actual, nueva, op) {
  return apiFetch('/auth/password', {
    ...op,
    method: 'PATCH',
    body: { current_password: actual, new_password: nueva },
  })
}

// ── Catálogos ──────────────────────────────────────
export function getSucursales(op) {
  return apiFetch('/consulta/sucursales', op)
}

export function getCategorias(op) {
  return apiFetch('/consulta/categorias', op)
}

// INV-26: buscador de productos de la vista de predicciones
export function getProductos({ busqueda, categoria, page, pageSize } = {}, op) {
  return apiFetch(`/consulta/productos${buildQS({ busqueda, categoria, page, page_size: pageSize })}`, op)
}

export function getProducto(idProducto, op) {
  return apiFetch(`/consulta/productos/${idProducto}`, op)
}

// INV-26: histórico en ventanas de 15 días hábiles (A1)
export function getVentasProducto(idProducto, { sucursalId, ventanas } = {}, op) {
  return apiFetch(
    `/consulta/productos/${idProducto}/ventas${buildQS({ sucursal_id: sucursalId, ventanas })}`, op)
}

// ── Dashboard / Reportes ───────────────────────────
export function getKPIs(sucursalId = null, op) {
  return apiFetch(`/reportes/kpis${buildQS({ sucursal_id: sucursalId })}`, op)
}

// Dashboard: { dias: 30, sucursalId }; Reportes: con fechas, categoría,
// agrupación y una serie por sucursal
export function getVentasTendencia(
  { dias, sucursalId, fechaInicio, fechaFin, categoria, agrupacion, porSucursal } = {}, op) {
  const qs = buildQS({
    dias, sucursal_id: sucursalId, fecha_inicio: fechaInicio, fecha_fin: fechaFin, categoria, agrupacion,
    por_sucursal: porSucursal,
  })
  return apiFetch(`/reportes/tendencias${qs}`, op)
}

export function getTopProductos(limite = 5, sucursalId = null, op) {
  return apiFetch(`/reportes/ventas/top-productos${buildQS({ limite, sucursal_id: sucursalId })}`, op)
}

// ── Reportes de ventas (vista Reportes, A9) ─────────
function filtrosReporte({ fechaInicio, fechaFin, sucursalId, categoria, agrupacion } = {}) {
  return buildQS({ fecha_inicio: fechaInicio, fecha_fin: fechaFin, sucursal_id: sucursalId, categoria, agrupacion })
}

export function getVentas(filtros, op) {
  return apiFetch(`/reportes/ventas${filtrosReporte(filtros)}`, op)
}

export function getComparativa(filtros, op) {
  return apiFetch(`/reportes/ventas/comparativa${filtrosReporte(filtros)}`, op)
}

export function getDistribucionCategorias({ fechaInicio, fechaFin, sucursalId } = {}, op) {
  return apiFetch(`/reportes/distribucion-categorias${filtrosReporte({ fechaInicio, fechaFin, sucursalId })}`, op)
}

export function getValorizado(sucursalId = null, op) {
  return apiFetch(`/consulta/inventario/valorizado${buildQS({ sucursal_id: sucursalId })}`, op)
}

// ── Inventario ─────────────────────────────────────
export function getInventarioResumen(sucursalId = null, op) {
  return apiFetch(`/consulta/inventario/resumen${buildQS({ sucursal_id: sucursalId })}`, op)
}

export function getInventario(params = {}, op) {
  return apiFetch(`/consulta/inventario${buildQS(params)}`, op)
}

export function getInventarioDetalle(idProducto, idSucursal, op) {
  return apiFetch(
    `/consulta/inventario/detalle${buildQS({ id_producto: idProducto, id_sucursal: idSucursal })}`, op)
}

// ── Alertas ────────────────────────────────────────
export function getAlertasResumen(sucursalId = null, op) {
  return apiFetch(`/alertas/resumen${buildQS({ sucursal_id: sucursalId })}`, op)
}

// Con page la API devuelve solo esa página (K2); sin ella, todas las alertas
export function getAlertas({ tipo, urgencia, sucursalId, page, pageSize } = {}, op) {
  const qs = buildQS({ tipo, urgencia, sucursal_id: sucursalId, page, page_size: pageSize })
  return apiFetch(`/alertas${qs}`, op)
}

// ── ML (INV-26 e INV-27) ───────────────────────────
// Pronóstico por ids, como Release 1 (G2)
export function predecir({ idProducto, idSucursal }, op) {
  return apiFetch('/ml/predict', {
    ...conTimeoutML(op),
    method: 'POST',
    body: { id_producto: idProducto, id_sucursal: idSucursal, horizonte: 15 },
  })
}

// Recomendaciones por nombre de sucursal (INV-23)
export function getRecomendacionesCompras({ sucursal, categoria, urgencia, incluirDetalle } = {}, op) {
  const qs = buildQS({ sucursal, categoria, urgencia, incluir_detalle: incluirDetalle })
  return apiFetch(`/ml/recomendaciones/compras${qs}`, conTimeoutML(op))
}

export function getRecomendacionesTransferencias({ sucursal, categoria, urgencia, incluirBalance } = {}, op) {
  const qs = buildQS({ sucursal, categoria, urgencia, incluir_balance: incluirBalance })
  return apiFetch(`/ml/recomendaciones/transferencias${qs}`, conTimeoutML(op))
}
