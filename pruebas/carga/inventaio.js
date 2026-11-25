// InventAI/o — Pruebas de carga de INV-41 (docs/INV-41-requerimientos.md, sección 4.4). Se corre con correr.sh.
//
// Variables de entorno:
//   ESCENARIO  lectura (por defecto) | vera | recorrido
//              lectura:   navegación (Dashboard con inventario, Alertas y Recomendaciones) más un login cada 2 s
//              vera:      3 usuarios distintos conversan con Vera a la vez, cada uno en serie
//              recorrido: una vuelta por cada pantalla con un usuario, para el escaneo pasivo de ZAP
//   PERFIL     10 | 20 | escalera (solo lectura). La escalera sube de 20 a 80 usuarios virtuales
//   BASE_URL   por defecto, el staging en CloudFront
//   CLAVES     la ruta del JSON {correo: clave} de las cuentas de staging, que nunca va al repositorio
//   ZAP        1 si el tráfico pasa por el proxy de ZAP (acepta su certificado)
//   DURACION   la de 10, 20 y el login (por defecto 5m), para ensayos cortos
//   PAUSA      lectora (de 5 a 15 s entre pantallas; por defecto en 10 y 20) | rapida (de 1 a 3 s; la escalera)
import http from 'k6/http'
import { check, fail, sleep } from 'k6'
import { Rate } from 'k6/metrics'

const BASE = (__ENV.BASE_URL || 'https://d32ramysc8c7pj.cloudfront.net').replace(/\/$/, '')
const ESCENARIO = __ENV.ESCENARIO || 'lectura'
const PERFIL = __ENV.PERFIL || '10'
if (!__ENV.CLAVES) throw new Error('falta CLAVES, la ruta del JSON de claves: correr.sh la pasa')
const CLAVES = JSON.parse(open(__ENV.CLAVES))
const CUENTAS = Object.entries(CLAVES).map(([email, password]) => ({ email, password }))
if (CUENTAS.length === 0) throw new Error('El archivo de claves no trae cuentas')

const JSON_CT = { 'Content-Type': 'application/json' }
const ESPERA_ML = '130s'                  // como el cliente web (decisión 4)
const DURACION = __ENV.DURACION || '5m'      // para ensayos cortos; las corridas oficiales son de 5 min

// El criterio 1 es sobre los 5xx; un 4xx (por ejemplo, un 403 de permisos) se ve en los checks
const errores5xx = new Rate('errores_5xx')

// ── Escenarios ──────────────────────────────────────

function escalera() {
  return {
    executor: 'ramping-vus', exec: 'navegar', startVUs: 0, gracefulRampDown: '30s',
    stages: [
      { duration: '1m', target: 20 }, { duration: '2m', target: 20 },
      { duration: '1m', target: 40 }, { duration: '2m', target: 40 },
      { duration: '1m', target: 60 }, { duration: '2m', target: 60 },
      { duration: '1m', target: 80 }, { duration: '2m', target: 80 },
    ],
  }
}

function escenarios() {
  if (ESCENARIO === 'vera') {
    return { vera: { executor: 'per-vu-iterations', exec: 'vera', vus: 3, iterations: 1, maxDuration: '8m' } }
  }
  if (ESCENARIO === 'recorrido') {
    return { recorrido: { executor: 'per-vu-iterations', exec: 'recorrido', vus: 1, iterations: 1, maxDuration: '5m' } }
  }
  if (ESCENARIO !== 'lectura') throw new Error(`ESCENARIO desconocido: ${ESCENARIO}`)
  const navegacion = PERFIL === 'escalera'
    ? escalera()
    : { executor: 'constant-vus', exec: 'navegar', vus: Number(PERFIL), duration: DURACION }
  if (!Number.isInteger(navegacion.vus ?? 1) || (navegacion.vus ?? 1) < 1) throw new Error(`PERFIL no válido: ${PERFIL}`)
  return {
    navegacion,
    login: {
      executor: 'constant-arrival-rate', exec: 'iniciarSesion', rate: 1, timeUnit: '2s',
      duration: PERFIL === 'escalera' ? '13m' : DURACION, preAllocatedVUs: 2, maxVUs: 4,
    },
  }
}

// Los umbrales por escenario hacen además que el resumen traiga cada uno por separado
function umbrales() {
  if (ESCENARIO === 'vera') {
    return {
      'http_req_duration{escenario:vera}': ['max<120000'],
      'checks{escenario:vera}': ['rate==1'],
      'errores_5xx{escenario:vera}': ['rate==0'],
    }
  }
  if (ESCENARIO === 'recorrido') return {}
  const u = {}
  for (const e of ['dashboard', 'alertas', 'recomendaciones', 'login']) {
    u[`http_req_duration{escenario:${e}}`] = ['p(95)<2000']
    u[`errores_5xx{escenario:${e}}`] = ['rate==0']
  }
  if (PERFIL === 'escalera') {
    // La escalera busca el límite: se corta sola con más del 5 % de errores
    u.errores_5xx = [{ threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '30s' }]
    u.http_req_failed = [{ threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '30s' }]
  }
  return u
}

export const options = {
  scenarios: escenarios(),
  thresholds: umbrales(),
  setupTimeout: '6m',
  insecureSkipTLSVerify: __ENV.ZAP === '1',
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)', 'count'],
  userAgent: 'inventaio-carga-inv41/1.0',
}

// ── Sesión ──────────────────────────────────────────

function entrar(cuenta, escenario) {
  const r = http.post(`${BASE}/api/auth/login`, JSON.stringify(cuenta),
    { headers: JSON_CT, tags: { escenario, name: 'POST /api/auth/login' } })
  errores5xx.add(r.status >= 500, { escenario })
  if (!check(r, { 'login 200': x => x.status === 200 }, { escenario })) return null
  return { access: r.json('access_token'), refresh: r.json('refresh_token') }
}

let sesion = null   // una por usuario virtual

function miSesion() {
  if (sesion) return sesion
  const cuenta = CUENTAS[(__VU - 1) % CUENTAS.length]
  const tokens = entrar(cuenta, 'inicio')
  if (!tokens) fail(`no se pudo iniciar sesión con la cuenta ${(__VU - 1) % CUENTAS.length + 1}`)
  const auth = { Authorization: `Bearer ${tokens.access}` }
  const yo = http.get(`${BASE}/api/auth/me`, { headers: auth, tags: { escenario: 'inicio', name: 'GET /api/auth/me' } })
  check(yo, { 'perfil 200': x => x.status === 200 }, { escenario: 'inicio' })
  const admin = yo.json('rol') === 'admin_sucursal'
  sesion = {
    ...tokens, auth,
    // Como el frontend (useSucursal): el administrador de sucursal pide la suya; los demás, todo
    sucursalId: admin ? yo.json('id_sucursal') : null,
    sucursal: admin ? yo.json('sucursal_nombre') : null,
  }
  return sesion
}

function qs(params) {
  const partes = Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

// Una petición del navegador: [método, ruta sin parámetros, parámetros]
function pedido(s, escenario, ruta, params = {}, espera = '60s') {
  return ['GET', `${BASE}${ruta}${qs(params)}`, null,
    { headers: s.auth, timeout: espera, tags: { escenario, name: `GET ${ruta}` } }]
}

// Varias a la vez, como las lanza una pantalla
function pantalla(escenario, pedidos) {
  const respuestas = http.batch(pedidos)
  for (const r of respuestas) {
    errores5xx.add(r.status >= 500, { escenario })
    check(r, { [`${escenario} 200`]: x => x.status === 200 }, { escenario })
  }
  return respuestas
}

// ── Pantallas ───────────────────────────────────────

function dashboard(s) {
  const id = { sucursal_id: s.sucursalId }
  pantalla('dashboard', [
    pedido(s, 'dashboard', '/api/reportes/kpis', id),
    pedido(s, 'dashboard', '/api/consulta/inventario/resumen', id),
    pedido(s, 'dashboard', '/api/alertas/resumen', id),
    pedido(s, 'dashboard', '/api/reportes/tendencias', { dias: 30, ...id }),
    pedido(s, 'dashboard', '/api/reportes/ventas/top-productos', { limite: 5, ...id }),
  ])
  pantalla('dashboard', [pedido(s, 'dashboard', '/api/consulta/inventario', { page: 1, page_size: 15, ...id })])
}

function alertas(s) {
  const id = { sucursal_id: s.sucursalId }
  pantalla('alertas', [
    pedido(s, 'alertas', '/api/alertas', { page: 1, page_size: 50, ...id }),
    pedido(s, 'alertas', '/api/alertas/resumen', id),
  ])
  pantalla('alertas', [
    pedido(s, 'alertas', '/api/alertas/ml', { page: 1, page_size: 50, ...id }, ESPERA_ML),
    pedido(s, 'alertas', '/api/alertas/ml', { page: 1, page_size: 1, ...id }, ESPERA_ML),
  ])
}

function recomendaciones(s) {
  const suc = { sucursal: s.sucursal }
  pantalla('recomendaciones', [
    pedido(s, 'recomendaciones', '/api/ml/recomendaciones/compras', { ...suc, incluir_detalle: false }, ESPERA_ML),
    pedido(s, 'recomendaciones', '/api/ml/recomendaciones/transferencias', { ...suc, incluir_balance: false },
      ESPERA_ML),
  ])
}

// Pausa entre pantallas (decisión D6 de los requerimientos). «lectora», de 5 a 15 s, es una persona que lee la
// pantalla: con ella se mide el criterio 1. «rapida», de 1 a 3 s, es la prueba de estrés de la escalera (criterio 6)
const PAUSA = __ENV.PAUSA || (PERFIL === 'escalera' ? 'rapida' : 'lectora')
const PAUSAS = { lectora: [5, 15], rapida: [1, 3] }
if (!PAUSAS[PAUSA]) throw new Error(`PAUSA desconocida: ${PAUSA}`)
const pausa = () => sleep(PAUSAS[PAUSA][0] + Math.random() * (PAUSAS[PAUSA][1] - PAUSAS[PAUSA][0]))

// ── Funciones de los escenarios ─────────────────────

export function setup() {
  const salud = http.get(`${BASE}/api/health`, { tags: { escenario: 'preparacion', name: 'GET /api/health' } })
  if (salud.status !== 200) fail(`staging no responde: ${salud.status}`)
  const version = `${salud.json('version')} · ${salud.json('commit')}`
  console.log(`Contra ${BASE}: ${version}, ${CUENTAS.length} cuentas, ${ESCENARIO}${ESCENARIO === 'lectura' ? ` ${PERFIL}, pausa ${PAUSA}` : ''}`)
  if (ESCENARIO !== 'lectura') return { version }

  // Caché caliente (H9): la primera consulta de recomendaciones tarda de 20 a 40 s
  const tokens = entrar(CUENTAS[0], 'preparacion')
  if (!tokens) fail('no se pudo iniciar sesión para calentar la caché')
  const s = { auth: { Authorization: `Bearer ${tokens.access}` } }
  const inicio = Date.now()
  const r = http.batch([
    pedido(s, 'preparacion', '/api/ml/recomendaciones/compras', { incluir_detalle: false }, ESPERA_ML),
    pedido(s, 'preparacion', '/api/ml/recomendaciones/transferencias', { incluir_balance: false }, ESPERA_ML),
    pedido(s, 'preparacion', '/api/alertas/ml', { page: 1, page_size: 1 }, ESPERA_ML),
  ])
  if (r.some(x => x.status !== 200)) fail(`no se pudo calentar la caché: ${r.map(x => x.status).join(', ')}`)
  console.log(`Caché caliente en ${((Date.now() - inicio) / 1000).toFixed(1)} s`)
  return { version }
}

export function navegar() {
  const s = miSesion()
  const dado = Math.random()
  if (dado < 0.5) dashboard(s)
  else if (dado < 0.75) alertas(s)
  else recomendaciones(s)
  pausa()
}

let turnoLogin = 0
export function iniciarSesion() {
  entrar(CUENTAS[(__VU * 7 + turnoLogin++) % CUENTAS.length], 'login')
}

// Preguntas sin nombres del negocio: valen para cualquier rol
const PREGUNTAS = [
  '¿Cuántas alertas críticas hay hoy?',
  '¿Qué productos debo pedir con más urgencia?',
  '¿Cómo van las ventas de este mes frente al mes pasado?',
  '¿Qué productos se están quedando sin existencias?',
  '¿Qué es el punto de pedido?',
]

export function vera() {
  // Tres cuentas distintas: el Core API admite una conversación por usuario
  const cuenta = CUENTAS[[0, 1, CUENTAS.length - 1][__VU - 1] ?? __VU - 1]
  const tokens = entrar(cuenta, 'inicio')
  if (!tokens) fail('no se pudo iniciar sesión para Vera')
  const fin = Date.now() + 5 * 60 * 1000
  for (let i = (__VU - 1) % PREGUNTAS.length; Date.now() < fin; i = (i + 1) % PREGUNTAS.length) {
    const r = http.post(`${BASE}/api/chat/message`,
      JSON.stringify({ mensajes: [{ rol: 'usuario', texto: PREGUNTAS[i] }] }),
      { headers: { ...JSON_CT, Accept: 'text/event-stream', Authorization: `Bearer ${tokens.access}` },
        timeout: '130s', tags: { escenario: 'vera', name: 'POST /api/chat/message' } })
    errores5xx.add(r.status >= 500, { escenario: 'vera' })
    check(r, {
      'vera 200': x => x.status === 200,
      'vera termina con done': x => typeof x.body === 'string' && x.body.includes('event: done'),
      'vera sin error': x => typeof x.body === 'string' && !x.body.includes('event: error'),
    }, { escenario: 'vera' })
    sleep(5 + Math.random() * 5)
  }
}

// Una vuelta por todo, con sesión, renovación y cierre: el escaneo pasivo de ZAP ve cada respuesta de la API
export function recorrido() {
  const s = miSesion()
  dashboard(s)
  alertas(s)
  recomendaciones(s)
  const consultas = [
    ['/api/consulta/sucursales', {}], ['/api/consulta/categorias', {}], ['/api/consulta/productos', { page: 1 }],
    ['/api/consulta/inventario/valorizado', {}], ['/api/reportes/ventas', {}], ['/api/chat/health', {}],
  ]
  pantalla('recorrido', consultas.map(([ruta, p]) => pedido(s, 'recorrido', ruta, p)))
  const renovada = http.post(`${BASE}/api/auth/refresh`, JSON.stringify({ refresh_token: s.refresh }),
    { headers: JSON_CT, tags: { escenario: 'recorrido', name: 'POST /api/auth/refresh' } })
  check(renovada, { 'renovar 200': x => x.status === 200 })
  const nuevo = renovada.json('refresh_token')
  const cierre = http.post(`${BASE}/api/auth/logout`, JSON.stringify({ refresh_token: nuevo }),
    { headers: { ...JSON_CT, Authorization: `Bearer ${renovada.json('access_token')}` },
      tags: { escenario: 'recorrido', name: 'POST /api/auth/logout' } })
  check(cierre, { 'cerrar 200': x => x.status === 200 })
  const otraVez = http.post(`${BASE}/api/auth/refresh`, JSON.stringify({ refresh_token: nuevo }),
    { headers: JSON_CT, tags: { escenario: 'recorrido', name: 'POST /api/auth/refresh' } })
  check(otraVez, { 'cerrada no renueva': x => x.status === 401 })
  http.post(`${BASE}/api/auth/login`, JSON.stringify({ email: 'nadie@inventaio.co', password: 'no-existe' }),
    { headers: JSON_CT, tags: { escenario: 'recorrido', name: 'POST /api/auth/login' } })
}
