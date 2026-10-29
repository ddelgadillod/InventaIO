/**
 * InventAI/o — Cliente del chat en streaming (INV-35)
 * POST /api/chat/message responde con SSE (contrato v1.1, docs/INV-36-api-chat.md).
 * apiFetch no sirve aquí: lee todo el cuerpo como JSON. Este módulo usa fetch y un
 * lector de SSE, y comparte con client.js los tokens y la renovación.
 */
import { ApiError, clearTokens, getTokens, textoDetalle, tryRefresh } from './client'

// Mismos límites que el Core API: más de esto da 422
export const MAX_MENSAJES = 13
export const MAX_CARACTERES_MENSAJE = 2000

/**
 * Lee un cuerpo SSE y entrega { evento, datos } por cada evento completo.
 * Un evento puede llegar partido en cualquier byte (también en medio de un
 * carácter UTF-8), así que se acumula hasta la línea en blanco que lo cierra.
 * Los comentarios (": ping") se ignoran.
 */
export async function* leerSSE(cuerpo) {
  const lector = cuerpo.getReader()
  const decodificador = new TextDecoder()
  let pendiente = ''
  try {
    for (;;) {
      const { done, value } = await lector.read()
      pendiente += decodificador.decode(value, { stream: !done })
      pendiente = pendiente.replace(/\r\n?/g, '\n')
      let corte
      while ((corte = pendiente.indexOf('\n\n')) !== -1) {
        const evento = interpretarEvento(pendiente.slice(0, corte))
        pendiente = pendiente.slice(corte + 2)
        if (evento) yield evento
      }
      if (done) break
    }
    // Un último evento sin la línea en blanco final también cuenta
    const resto = interpretarEvento(pendiente)
    if (resto) yield resto
  } finally {
    lector.cancel().catch(() => {})
  }
}

function interpretarEvento(bloque) {
  let evento = 'message'
  const datos = []
  for (const linea of bloque.split('\n')) {
    if (!linea || linea.startsWith(':')) continue
    const dosPuntos = linea.indexOf(':')
    const campo = dosPuntos === -1 ? linea : linea.slice(0, dosPuntos)
    let valor = dosPuntos === -1 ? '' : linea.slice(dosPuntos + 1)
    if (valor.startsWith(' ')) valor = valor.slice(1)
    if (campo === 'event') evento = valor
    else if (campo === 'data') datos.push(valor)
  }
  if (!datos.length) return null
  try {
    return { evento, datos: JSON.parse(datos.join('\n')) }
  } catch {
    return null
  }
}

// Una petición al chat con el token. Al token le quedan menos de 120 s: el Core API lo
// rechaza con 401 antes de abrir el flujo, y se renueva una vez (Y2)
async function pedir(ruta, init, signal) {
  const una = async () => {
    const { access } = getTokens()
    try {
      return await fetch(ruta, {
        ...init,
        headers: { ...init.headers, ...(access ? { Authorization: `Bearer ${access}` } : {}) },
        signal,
      })
    } catch {
      if (signal?.aborted) throw new ApiError(0, 'Consulta cancelada', { cancelada: true })
      throw new ApiError(0, 'No hay conexión con el servidor')
    }
  }
  let res = await una()
  if (res.status === 401) {
    if (await tryRefresh()) res = await una()
    if (res.status === 401) {
      clearTokens()
      window.location.href = '/login'
      throw new ApiError(401, 'Sesión expirada')
    }
  }
  return res
}

/**
 * Envía la conversación y devuelve el generador de eventos del agente.
 * `mensajes` va como [{ rol: 'usuario' | 'agente', texto }] y termina en una
 * pregunta del usuario. Lanza ApiError ante un error HTTP: 401 (tras intentar
 * renovar el token una vez), 422, 429 (con `retryAfter` en segundos) o 5xx.
 */
export async function enviarMensaje(mensajes, { signal } = {}) {
  const res = await pedir('/api/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ mensajes }),
  }, signal)
  if (!res.ok) {
    const datos = await res.json().catch(() => ({}))
    const error = new ApiError(res.status, textoDetalle(datos?.detail, res.status))
    const espera = Number(res.headers.get('Retry-After'))
    error.retryAfter = Number.isFinite(espera) && espera > 0 ? espera : null
    throw error
  }
  if (!res.body) throw new ApiError(502, 'La respuesta del agente no llegó en streaming')
  return leerSSE(res.body)
}

/**
 * ¿Vera puede responder? (M3) GET /api/chat/health al abrir el panel.
 * { listo: true, modelo } o { listo: false, motivo }: `ollama_no_alcanzable`,
 * `modelo_no_descargado` o `agente_no_disponible` (503 del Core API), o
 * `sin_conexion`. Cualquier otra respuesta da null: no se sabe, y no bloquea.
 * apiFetch no sirve: del 503 descarta el `{ motivo }`.
 */
export async function saludVera({ signal } = {}) {
  let res
  try {
    res = await pedir('/api/chat/health', { method: 'GET' }, signal)
  } catch (e) {
    if (e.status === 0 && !e.cancelada) return { listo: false, motivo: 'sin_conexion' }
    throw e
  }
  const datos = await res.json().catch(() => ({}))
  if (res.ok) return { listo: true, modelo: datos?.modelo ?? null }
  if ([502, 503, 504].includes(res.status)) return { listo: false, motivo: datos?.detail?.motivo ?? 'agente_no_disponible' }
  return null
}
