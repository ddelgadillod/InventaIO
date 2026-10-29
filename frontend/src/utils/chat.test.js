import { describe, expect, it } from 'vitest'
import {
  aplicarEvento, describirError, etapaDe, hayHerramientaDenegada, historialParaEnviar,
  mensajeAgenteVacio, mensajeUsuario, seRecortaLaConversacion,
} from './chat'
import { FLUJO_403, FLUJO_ALERTAS } from '../test/vera'

const aplicarTodos = (eventos, msg = mensajeAgenteVacio()) => eventos
  .filter(e => typeof e !== 'string')
  .reduce((m, [evento, datos]) => aplicarEvento(m, { evento, datos }), msg)

const respondido = texto => ({ ...mensajeAgenteVacio(), texto, terminado: true })

describe('aplicarEvento', () => {
  it('arma el mensaje del flujo real: herramienta, tabla, texto y done', () => {
    const msg = aplicarTodos(FLUJO_ALERTAS)
    expect(msg.modelo).toBe('qwen3:8b')
    expect(msg.herramientas).toEqual([{
      id: '1-1', nombre: 'resumen_alertas', estado: 'ok', lenta: false, ms: 1590, codigo: null,
      etiqueta: 'Resumen de alertas · GLORIETA',
    }])
    expect(msg.datos[0].filas[0].media).toBe('1.092')
    expect(msg.texto).toBe('En GLORIETA hay **243** alertas críticas.')
    expect(msg).toMatchObject({
      terminado: true, respaldo: false, fidelidad: 'ok', fechasDatos: ['2025-12-31'],
      sugerencias: ['¿Quieres ver las alertas críticas?'], msTotal: 2988, turnosRecortados: 0,
    })
  })

  it('el 403 queda en la herramienta; la lentitud de `inicio` se conserva al cerrar', () => {
    expect(hayHerramientaDenegada(aplicarTodos(FLUJO_403))).toBe(true)
    expect(hayHerramientaDenegada(aplicarTodos(FLUJO_ALERTAS))).toBe(false)
    const lenta = aplicarTodos([
      ['tool', { id: 'x', nombre: 'recomendar_compras', estado: 'inicio', lenta: true }],
      ['tool', { id: 'x', nombre: 'recomendar_compras', estado: 'ok' }],
    ])
    expect(lenta.herramientas[0]).toMatchObject({ lenta: true, etiqueta: 'recomendar_compras', estado: 'ok' })
  })

  it('done con datos faltantes, error, respaldo y eventos desconocidos', () => {
    let msg = aplicarTodos([['done', { respaldo: true, sugerencias: ['a', 'b', 'c', 'd'] }]])
    expect(msg).toMatchObject({ respaldo: true, fechasDatos: [], sugerencias: ['a', 'b', 'c'], fidelidad: null, msTotal: null })
    msg = aplicarTodos([['done', {}]])
    expect(msg.sugerencias).toEqual([])
    msg = aplicarTodos([['error', { codigo: 'tiempo_agotado' }], ['otro', {}], ['token', {}], ['meta', {}]])
    expect(msg.error).toEqual({ codigo: 'tiempo_agotado', mensaje: '' })
    expect(msg.texto).toBe('')
    expect(msg.modelo).toBeNull()
  })
})

describe('etapaDe', () => {
  it('conectando → analizando → consultando → verificando → redactando', () => {
    expect(etapaDe(null)).toBeNull()
    const vacio = mensajeAgenteVacio()
    expect(etapaDe(vacio)).toBe('conectando')
    const conMeta = aplicarTodos(FLUJO_ALERTAS.slice(0, 1))
    expect(etapaDe(conMeta)).toBe('analizando')
    expect(etapaDe(aplicarTodos(FLUJO_ALERTAS.slice(0, 2)))).toBe('consultando')
    expect(etapaDe(aplicarTodos(FLUJO_ALERTAS.slice(0, 5)))).toBe('verificando')
    expect(etapaDe(aplicarTodos(FLUJO_ALERTAS.slice(0, 6)))).toBe('redactando')
  })
})

describe('historialParaEnviar', () => {
  it('solo turnos completos y verificados, más la pregunta nueva', () => {
    const mensajes = [
      mensajeUsuario('uno'), respondido('r1'),
      mensajeUsuario('fallida'), { ...mensajeAgenteVacio(), error: { codigo: 'x' } },
      mensajeUsuario('respaldo'), { ...respondido('No pude redactar…'), respaldo: true },
      mensajeUsuario('sin respuesta'),
      mensajeUsuario('nueva'),
    ]
    expect(historialParaEnviar(mensajes)).toEqual([
      { rol: 'usuario', texto: 'uno' }, { rol: 'agente', texto: 'r1' }, { rol: 'usuario', texto: 'nueva' },
    ])
  })

  it('recorta a 13 mensajes empezando por una pregunta (Y4)', () => {
    const mensajes = []
    for (let i = 0; i < 10; i++) mensajes.push(mensajeUsuario(`p${i}`), respondido(`r${i}`))
    mensajes.push(mensajeUsuario('nueva'))
    const enviado = historialParaEnviar(mensajes)
    expect(enviado).toHaveLength(13)
    expect(enviado[0]).toEqual({ rol: 'usuario', texto: 'p4' })
    expect(enviado.at(-1)).toEqual({ rol: 'usuario', texto: 'nueva' })
    expect(seRecortaLaConversacion(mensajes)).toBe(true)
    expect(seRecortaLaConversacion(mensajes.slice(0, 12))).toBe(false)
  })

  it('recorta por caracteres: 2.000 por mensaje y 16.000 en total', () => {
    const largo = 'x'.repeat(2500)
    const mensajes = []
    for (let i = 0; i < 5; i++) mensajes.push(mensajeUsuario(largo), respondido(largo))
    mensajes.push(mensajeUsuario('nueva'))
    const enviado = historialParaEnviar(mensajes)
    expect(enviado.every(m => m.texto.length <= 2000)).toBe(true)
    expect(enviado.reduce((s, m) => s + m.texto.length, 0)).toBeLessThanOrEqual(16000)
    expect(enviado[0].rol).toBe('usuario')
    expect(enviado).toHaveLength(7)
  })
})

describe('describirError', () => {
  it('eventos `error` del flujo por código', () => {
    expect(describirError(null)).toBeNull()
    expect(describirError({ codigo: 'tiempo_agotado' })).toMatchObject({ titulo: 'La consulta tardó demasiado', reintentable: true })
    expect(describirError({ codigo: 'modelo_no_descargado' })).toMatchObject({ titulo: 'Vera no está disponible', reintentable: false })
    expect(describirError({ codigo: 'llm_no_disponible' }).reintentable).toBe(true)
    expect(describirError({ codigo: 'solicitud_invalida' }).reintentable).toBe(false)
    expect(describirError({ codigo: 'respuesta_invalida' }).titulo).toBe('Vera dio una respuesta inválida')
    expect(describirError({ codigo: 'nuevo', mensaje: 'Detalle' })).toEqual({ titulo: 'Algo falló en Vera', detalle: 'Detalle', reintentable: true })
    expect(describirError({ codigo: 'nuevo' }).detalle).toBe('Intenta de nuevo.')
  })

  it('errores HTTP del cliente', () => {
    expect(describirError({ status: 0, cancelada: true })).toBeNull()
    expect(describirError({ status: 401 })).toMatchObject({ titulo: 'Tu sesión expiró', reintentable: false })
    expect(describirError({ status: 403 })).toMatchObject({ titulo: 'No tienes permiso', reintentable: false })
    expect(describirError({ status: 422, detail: 'mensajes: muy largo' }).detalle).toBe('mensajes: muy largo')
    expect(describirError({ status: 422 }).detalle).toBe('La pregunta no cumple los límites del chat.')
    expect(describirError({ status: 429 })).toMatchObject({ titulo: 'Vera está atendiendo otra consulta', reintentable: true })
    expect(describirError({ status: 0, detail: 'No hay conexión con el servidor' }).titulo).toBe('Sin conexión con el servidor')
    expect(describirError({ status: 0 }).detalle).toBe('Revisa tu conexión.')
    expect(describirError({ status: 504 })).toMatchObject({ titulo: 'Vera no está disponible', reintentable: true })
  })
})
