import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import useChat, { DEMORA_MS } from './useChat'
import { simularApi, textoSSE } from '../test/utils'
import { FLUJO_ALERTAS, META } from '../test/vera'

const RUTA = 'POST /api/chat/message'

// Un flujo que entrega `eventos` y queda abierto hasta que se aborta la petición
function flujoAbierto(eventos = [META, ['token', { texto: 'Hay ' }]]) {
  vi.stubGlobal('fetch', vi.fn(async (_url, { signal }) => new Response(new ReadableStream({
    start(control) {
      control.enqueue(new TextEncoder().encode(textoSSE(eventos)))
      signal.addEventListener('abort', () => control.error(new DOMException('Aborted', 'AbortError')))
    },
  }), { status: 200 })))
}

describe('useChat', () => {
  it('reposo → enviando → transmitiendo → reposo, con el mensaje armado', async () => {
    const api = simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS), demoraMs: 20 } })
    const { result } = renderHook(() => useChat())
    expect(result.current.fase).toBe('reposo')
    act(() => { result.current.enviar('  ¿Alertas en GLORIETA?  ') })
    expect(result.current.fase).toBe('enviando')
    expect(result.current.ocupado).toBe(true)
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    const [usuario, vera] = result.current.mensajes
    expect(usuario).toMatchObject({ rol: 'usuario', texto: '¿Alertas en GLORIETA?' })
    expect(vera).toMatchObject({ rol: 'agente', terminado: true, texto: 'En GLORIETA hay **243** alertas críticas.' })
    expect(api.llamadas[0].body.mensajes).toEqual([{ rol: 'usuario', texto: '¿Alertas en GLORIETA?' }])
  })

  it('no envía vacío ni con otra respuesta en curso; la segunda pregunta lleva el historial', async () => {
    const api = simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS), demoraMs: 20 } })
    const { result } = renderHook(() => useChat())
    let enviado
    act(() => { enviado = result.current.enviar('   ') })
    expect(enviado).toBe(false)
    act(() => { result.current.enviar('una') })
    act(() => { enviado = result.current.enviar('otra') })
    expect(enviado).toBe(false)
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    act(() => { result.current.enviar('dos') })
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    expect(api.llamadas[1].body.mensajes.map(m => m.rol)).toEqual(['usuario', 'agente', 'usuario'])
  })

  it('un evento `error` deja la fase en error; reintentar repite la pregunta', async () => {
    let n = 0
    simularApi({
      [RUTA]: () => (++n === 1
        ? { sse: textoSSE([META, ['error', { codigo: 'tiempo_agotado', mensaje: '…' }]]) }
        : { sse: textoSSE(FLUJO_ALERTAS) }),
    })
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await waitFor(() => expect(result.current.fase).toBe('error'))
    expect(result.current.error).toMatchObject({ titulo: 'La consulta tardó demasiado', reintentable: true })
    act(() => { result.current.reintentar() })
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    expect(result.current.error).toBeNull()
    expect(result.current.mensajes.map(m => m.rol)).toEqual(['usuario', 'agente'])
    expect(result.current.mensajes[1].terminado).toBe(true)
  })

  it('un flujo que termina sin `done` es un corte (X5-b de INV-36)', async () => {
    simularApi({ [RUTA]: { sse: textoSSE([META, ['token', { texto: 'En GLO' }]]) } })
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await waitFor(() => expect(result.current.fase).toBe('error'))
    expect(result.current.error.titulo).toBe('La respuesta de Vera se cortó')
    expect(result.current.mensajes[1]).toMatchObject({ incompleto: true, texto: 'En GLO' })
  })

  // Con relojes falsos no sirve waitFor: se avanza el reloj y se vacían las promesas
  const avanzar = ms => act(() => vi.advanceTimersByTimeAsync(ms))

  it('un 429 espera Retry-After y reintenta solo; tras dos intentos, queda el error', async () => {
    vi.useFakeTimers()
    let n = 0
    simularApi({
      [RUTA]: () => (++n <= 3
        ? { status: 429, body: { detail: 'ocupado' }, headers: { 'Retry-After': '3' } }
        : { sse: textoSSE(FLUJO_ALERTAS) }),
    })
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await avanzar(0)
    expect(result.current.fase).toBe('espera')
    expect(result.current.esperaS).toBe(3)
    await avanzar(2999)
    expect(n).toBe(1)
    await avanzar(1)
    expect(n).toBe(2)
    expect(result.current.fase).toBe('espera')
    await avanzar(3000)
    expect(n).toBe(3)
    expect(result.current.fase).toBe('error')
    expect(result.current.error.titulo).toBe('Vera está atendiendo otra consulta')
    act(() => { result.current.reintentar() })
    await avanzar(0)
    expect(n).toBe(4)
    expect(result.current.fase).toBe('reposo')
  })

  it('un 429 sin Retry-After espera 5 s; detener cancela la espera', async () => {
    vi.useFakeTimers()
    const api = simularApi({ [RUTA]: { status: 429, body: {} } })
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await avanzar(0)
    expect(result.current.esperaS).toBe(5)
    act(() => { result.current.detener() })
    expect(result.current.fase).toBe('reposo')
    expect(result.current.esperaS).toBeNull()
    await avanzar(10_000)
    expect(api.llamadas).toHaveLength(1)
  })

  it('detener a mitad del flujo deja lo recibido, marcado, sin mostrar un error', async () => {
    flujoAbierto()
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await waitFor(() => expect(result.current.mensajes[1].texto).toBe('Hay '))
    expect(result.current.fase).toBe('transmitiendo')
    act(() => { result.current.detener() })
    await act(async () => {})
    expect(result.current.fase).toBe('reposo')
    expect(result.current.error).toBeNull()
    expect(result.current.mensajes[1]).toMatchObject({ incompleto: true, detenido: true })
    // Sin nada en curso, detener no hace nada
    act(() => { result.current.detener() })
    expect(result.current.fase).toBe('reposo')
  })

  it('«Nueva conversación» corta el flujo y vacía la memoria; reintentar sin preguntas no hace nada', async () => {
    flujoAbierto()
    const { result } = renderHook(() => useChat())
    act(() => { result.current.reintentar() })
    expect(result.current.fase).toBe('reposo')
    act(() => { result.current.enviar('pregunta') })
    await waitFor(() => expect(result.current.fase).toBe('transmitiendo'))
    act(() => { result.current.reintentar() }) // ocupado: no hace nada
    act(() => { result.current.nuevaConversacion() })
    await act(async () => {})
    expect(result.current.mensajes).toEqual([])
    expect(result.current.fase).toBe('reposo')
    expect(result.current.error).toBeNull()
  })

  it('una pregunta nueva tras un error HTTP descarta la respuesta vacía', async () => {
    let n = 0
    simularApi({ [RUTA]: () => (++n === 1 ? { status: 503, body: {} } : { sse: textoSSE(FLUJO_ALERTAS) }) })
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('primera') })
    await waitFor(() => expect(result.current.fase).toBe('error'))
    expect(result.current.error.titulo).toBe('Vera no está disponible')
    act(() => { result.current.enviar('segunda') })
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    expect(result.current.mensajes.map(m => m.texto.slice(0, 7))).toEqual(['primera', 'segunda', 'En GLOR'])
  })

  it('una pregunta nueva conserva la respuesta detenida que ya traía una tabla, aunque no tenga texto', async () => {
    // meta, la herramienta, el ping y la tabla; detenida antes del primer token (corrida de la §19, K-08)
    flujoAbierto(FLUJO_ALERTAS.slice(0, 5))
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('primera') })
    await waitFor(() => expect(result.current.mensajes[1].datos).toHaveLength(1))
    act(() => { result.current.detener() })
    await act(async () => {})
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    act(() => { result.current.enviar('segunda') })
    await waitFor(() => expect(result.current.fase).toBe('reposo'))
    expect(result.current.mensajes.map(m => m.rol)).toEqual(['usuario', 'agente', 'usuario', 'agente'])
    expect(result.current.mensajes[1]).toMatchObject({ texto: '', detenido: true })
    expect(result.current.mensajes[1].datos).toHaveLength(1)
  })

  it('avisa la demora tras 10 s sin eventos; cada evento reinicia la cuenta (M2)', async () => {
    vi.useFakeTimers()
    const avanzar = ms => act(() => vi.advanceTimersByTimeAsync(ms))
    let flujo
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({ start(c) { flujo = c } }), { status: 200 })))
    const cod = new TextEncoder()
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await avanzar(DEMORA_MS - 1)
    expect(result.current.demorado).toBe(false)
    await avanzar(1)
    expect(result.current.demorado).toBe(true)
    // Llega `meta`: se va el aviso y la cuenta vuelve a empezar
    flujo.enqueue(cod.encode(textoSSE([META])))
    await avanzar(0)
    expect(result.current.demorado).toBe(false)
    // El ping no es un evento: no reinicia la cuenta
    await avanzar(DEMORA_MS / 2)
    flujo.enqueue(cod.encode(': ping\n\n'))
    await avanzar(DEMORA_MS / 2)
    expect(result.current.demorado).toBe(true)
    // Al terminar, se apaga y no vuelve
    flujo.enqueue(cod.encode(textoSSE([['token', { texto: 'Hola' }], ['done', {}]])))
    flujo.close()
    await avanzar(0)
    expect(result.current.fase).toBe('reposo')
    expect(result.current.demorado).toBe(false)
    await avanzar(DEMORA_MS * 2)
    expect(result.current.demorado).toBe(false)
  })

  it('detener apaga el aviso de demora', async () => {
    vi.useFakeTimers()
    const avanzar = ms => act(() => vi.advanceTimersByTimeAsync(ms))
    vi.stubGlobal('fetch', vi.fn(async (_u, { signal }) => new Response(new ReadableStream({
      start(c) { signal.addEventListener('abort', () => c.error(new DOMException('Aborted', 'AbortError'))) },
    }), { status: 200 })))
    const { result } = renderHook(() => useChat())
    act(() => { result.current.enviar('pregunta') })
    await avanzar(DEMORA_MS)
    expect(result.current.demorado).toBe(true)
    act(() => { result.current.detener() })
    await avanzar(0)
    expect(result.current.demorado).toBe(false)
  })
})
