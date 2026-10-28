import { describe, expect, it, vi } from 'vitest'
import { enviarMensaje, leerSSE, saludVera } from './chat'
import { flujoDe, simularApi, textoSSE } from '../test/utils'
import { FLUJO_ALERTAS } from '../test/vera'

async function todos(generador) {
  const lista = []
  for await (const e of generador) lista.push(e)
  return lista
}

const PREGUNTA = [{ rol: 'usuario', texto: '¿Cuántas alertas críticas hay en GLORIETA?' }]

describe('leerSSE', () => {
  it('arma los eventos aunque lleguen partidos a mitad de evento, de línea y de carácter', async () => {
    const texto = textoSSE(FLUJO_ALERTAS)
    const bytes = new TextEncoder().encode(texto)
    // De 7 en 7 bytes: corta la «í» de «Crítica» y los separadores en cualquier punto
    const fragmentos = []
    for (let i = 0; i < bytes.length; i += 7) fragmentos.push(bytes.slice(i, i + 7))
    const eventos = await todos(leerSSE(flujoDe(fragmentos)))
    expect(eventos.map(e => e.evento)).toEqual(['meta', 'tool', 'tool', 'data', 'token', 'token', 'done'])
    expect(eventos[3].datos.columnas[1].titulo).toBe('Crítica')
    expect(eventos[3].datos.filas[0].media).toBe('1.092')
  })

  it('varios eventos en un fragmento, CRLF, el ping y un último evento sin línea en blanco', async () => {
    const flujo = flujoDe([
      'event: meta\r\ndata: {"modelo":"m"}\r\n\r\n: ping\n\nevent: token\ndata: {"texto":"a"}\n\n',
      'event: token\ndata: {"texto":"b"}',
    ])
    const eventos = await todos(leerSSE(flujo))
    expect(eventos).toEqual([
      { evento: 'meta', datos: { modelo: 'm' } },
      { evento: 'token', datos: { texto: 'a' } },
      { evento: 'token', datos: { texto: 'b' } },
    ])
  })

  it('ignora un data que no es JSON y usa «message» si no hay event; une varias líneas data', async () => {
    const flujo = flujoDe('event: token\ndata: {roto\n\ndata: {"a":\ndata: 1}\n\nevent\ndata:{"b":2}\n\n')
    expect(await todos(leerSSE(flujo))).toEqual([
      { evento: 'message', datos: { a: 1 } },
      { evento: '', datos: { b: 2 } },
    ])
  })
})

describe('enviarMensaje', () => {
  it('manda la conversación con el token y entrega el flujo', async () => {
    localStorage.setItem('access_token', 'tok')
    const api = simularApi({ 'POST /api/chat/message': { sse: textoSSE(FLUJO_ALERTAS) } })
    const eventos = await todos(await enviarMensaje(PREGUNTA))
    expect(eventos).toHaveLength(7)
    expect(api.llamadas[0].body).toEqual({ mensajes: PREGUNTA })
    expect(api.llamadas[0].headers.Authorization).toBe('Bearer tok')
    expect(api.llamadas[0].headers.Accept).toBe('text/event-stream')
  })

  it('ante un 401 renueva el token y reintenta una vez (token por vencer, C4)', async () => {
    localStorage.setItem('access_token', 'viejo')
    localStorage.setItem('refresh_token', 'r1')
    let intentos = 0
    const api = simularApi({
      'POST /api/chat/message': ({ headers }) => {
        intentos += 1
        return headers.Authorization === 'Bearer nuevo'
          ? { sse: textoSSE(FLUJO_ALERTAS) }
          : { status: 401, body: { detail: 'Token por vencer' } }
      },
      'POST /api/auth/refresh': { body: { access_token: 'nuevo', refresh_token: 'r2' } },
    })
    const eventos = await todos(await enviarMensaje(PREGUNTA))
    expect(eventos).toHaveLength(7)
    expect(intentos).toBe(2)
    expect(localStorage.getItem('refresh_token')).toBe('r2')
    expect(api.llamadas.map(l => l.ruta)).toEqual(['/api/chat/message', '/api/auth/refresh', '/api/chat/message'])
  })

  it('si no se puede renovar, cierra la sesión y manda al login', async () => {
    localStorage.setItem('access_token', 'viejo')
    vi.stubGlobal('location', { href: '/' })
    simularApi({ 'POST /api/chat/message': { status: 401, body: {} } })
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 401 })
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('429 trae los segundos de Retry-After; sin la cabecera, retryAfter es null', async () => {
    simularApi({ 'POST /api/chat/message': { status: 429, body: { detail: 'Otro flujo en curso' }, headers: { 'Retry-After': '7' } } })
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 429, retryAfter: 7, detail: 'Otro flujo en curso' })
    simularApi({ 'POST /api/chat/message': { status: 503, body: {} } })
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 503, retryAfter: null })
  })

  it('el 422 de validación llega como texto', async () => {
    simularApi({
      'POST /api/chat/message': { status: 422, body: { detail: [{ loc: ['body', 'mensajes'], msg: 'Demasiados mensajes' }] } },
    })
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 422, detail: 'mensajes: Demasiados mensajes' })
  })

  it('sin conexión, cancelada o sin cuerpo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 0, detail: 'No hay conexión con el servidor' })

    const ctrl = new AbortController()
    ctrl.abort()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')))
    await expect(enviarMensaje(PREGUNTA, { signal: ctrl.signal })).rejects.toMatchObject({ cancelada: true })

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true, body: null }))
    await expect(enviarMensaje(PREGUNTA)).rejects.toMatchObject({ status: 502 })
  })
})

describe('saludVera (M3)', () => {
  const RUTA = 'GET /api/chat/health'

  it('listo con el modelo; 503 con su motivo', async () => {
    simularApi({ [RUTA]: { body: { estado: 'listo', modelo: 'qwen3:8b' } } })
    expect(await saludVera()).toEqual({ listo: true, modelo: 'qwen3:8b' })
    simularApi({ [RUTA]: { status: 503, body: { detail: { motivo: 'ollama_no_alcanzable' } } } })
    expect(await saludVera()).toEqual({ listo: false, motivo: 'ollama_no_alcanzable' })
  })

  it('502 o 504 sin cuerpo útil: el agente no está disponible; sin conexión, sin_conexion', async () => {
    simularApi({ [RUTA]: { status: 502, body: {} } })
    expect(await saludVera()).toEqual({ listo: false, motivo: 'agente_no_disponible' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>', { status: 504 })))
    expect(await saludVera()).toEqual({ listo: false, motivo: 'agente_no_disponible' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect(await saludVera()).toEqual({ listo: false, motivo: 'sin_conexion' })
  })

  it('otra respuesta no se sabe (null) y una cancelada se propaga', async () => {
    simularApi({ [RUTA]: { status: 500, body: {} } })
    expect(await saludVera()).toBeNull()
    simularApi({ [RUTA]: { body: {} } })
    expect(await saludVera()).toEqual({ listo: true, modelo: null })
    const ctrl = new AbortController()
    ctrl.abort()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')))
    await expect(saludVera({ signal: ctrl.signal })).rejects.toMatchObject({ cancelada: true })
  })
})
