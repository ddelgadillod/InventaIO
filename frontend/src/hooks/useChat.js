/**
 * InventAI/o — Estado de la conversación con Vera (INV-35)
 * Máquina de estados: reposo → enviando → transmitiendo → reposo | error.
 * `enviando` es hasta el primer evento del flujo; `espera` es el 429 (otro flujo
 * en curso), que se reintenta solo tras `Retry-After`. La conversación vive solo
 * en la memoria de la sesión (CA 9).
 * `demorado` (M2): pasaron 10 s sin eventos con una respuesta en curso; el `: ping`
 * no cuenta, porque el lector de SSE no lo entrega.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { enviarMensaje } from '../api/chat'
import {
  MAX_MENSAJES_GUARDADOS, aplicarEvento, describirError, historialParaEnviar,
  mensajeAgenteVacio, mensajeUsuario,
} from '../utils/chat'

const ESPERA_POR_DEFECTO_S = 5
const REINTENTOS_AUTOMATICOS = 2
export const DEMORA_MS = 10_000

export default function useChat() {
  const [mensajes, setMensajes] = useState([])
  const [fase, setFase] = useState('reposo')
  const [error, setError] = useState(null)
  const [esperaS, setEsperaS] = useState(null)
  const [demorado, setDemorado] = useState(false)
  const control = useRef(null) // AbortController del flujo vigente
  const temporizador = useRef(null)
  const relojDemora = useRef(null)
  const transmitirRef = useRef(null) // para reintentar tras el 429 desde el temporizador

  const limpiarEspera = useCallback(() => {
    clearTimeout(temporizador.current)
    temporizador.current = null
    setEsperaS(null)
  }, [])

  // Cada evento reinicia la cuenta de la demora; sin respuesta en curso, se apaga
  const vigilarDemora = useCallback((activa = true) => {
    clearTimeout(relojDemora.current)
    setDemorado(false)
    relojDemora.current = activa ? setTimeout(() => setDemorado(true), DEMORA_MS) : null
  }, [])

  const cancelar = useCallback(() => {
    control.current?.abort()
    control.current = null
    clearTimeout(relojDemora.current)
    setDemorado(false)
    limpiarEspera()
  }, [limpiarEspera])

  useEffect(() => cancelar, [cancelar])

  const cambiarAgente = useCallback((id, cambio) => {
    setMensajes(lista => lista.map(m => (m.id === id ? cambio(m) : m)))
  }, [])

  // Manda la conversación tal como está en `lista` (termina en la pregunta) y llena `idAgente`
  const transmitir = useCallback(async (lista, idAgente, intento = 0) => {
    const ctrl = new AbortController()
    control.current = ctrl
    setError(null)
    setFase('enviando')
    vigilarDemora()
    try {
      const eventos = await enviarMensaje(historialParaEnviar(lista), { signal: ctrl.signal })
      setFase('transmitiendo')
      let termino = false
      for await (const evento of eventos) {
        if (ctrl.signal.aborted) return
        vigilarDemora()
        cambiarAgente(idAgente, m => aplicarEvento(m, evento))
        if (evento.evento === 'done') termino = true
        if (evento.evento === 'error') {
          setError(describirError(evento.datos))
          setFase('error')
          return
        }
      }
      // Sin `done` ni `error`: el flujo se cortó a mitad (X5-b de INV-36)
      if (!termino) {
        cambiarAgente(idAgente, m => ({ ...m, incompleto: true }))
        setError({ titulo: 'La respuesta de Vera se cortó', detalle: 'Se perdió la conexión antes de terminar.', reintentable: true })
        setFase('error')
        return
      }
      setFase('reposo')
    } catch (e) {
      // Detener o «Nueva conversación» a mitad de la lectura: la falla no es un error para el usuario
      if (e.cancelada || ctrl.signal.aborted) return
      if (e.status === 429 && intento < REINTENTOS_AUTOMATICOS) {
        const segundos = e.retryAfter ?? ESPERA_POR_DEFECTO_S
        setFase('espera')
        setEsperaS(segundos)
        temporizador.current = setTimeout(() => {
          setEsperaS(null)
          transmitirRef.current(lista, idAgente, intento + 1)
        }, segundos * 1000)
        return
      }
      setError(describirError(e))
      setFase('error')
    } finally {
      // Solo si no empezó otro flujo mientras tanto (detener y volver a preguntar)
      if (control.current === ctrl) {
        control.current = null
        vigilarDemora(false)
      }
    }
  }, [cambiarAgente, vigilarDemora])

  useEffect(() => { transmitirRef.current = transmitir }, [transmitir])

  const enviar = useCallback((texto) => {
    const pregunta = texto.trim()
    if (!pregunta || ['enviando', 'transmitiendo', 'espera'].includes(fase)) return false
    // Una respuesta fallida sin contenido se descarta: la pregunta nueva la reemplaza
    const previos = mensajes.filter(m => !(m.rol === 'agente' && !m.terminado && !m.texto))
    const agente = mensajeAgenteVacio()
    const lista = [...previos, mensajeUsuario(pregunta)]
    setMensajes([...lista, agente].slice(-MAX_MENSAJES_GUARDADOS))
    transmitir(lista, agente.id)
    return true
  }, [fase, mensajes, transmitir])

  // Repite la última pregunta (tras un error, un corte o al detener)
  const reintentar = useCallback(() => {
    if (['enviando', 'transmitiendo', 'espera'].includes(fase)) return
    const actuales = mensajes
    const ultimoUsuario = actuales.findLastIndex(m => m.rol === 'usuario')
    if (ultimoUsuario === -1) return
    const lista = actuales.slice(0, ultimoUsuario + 1)
    const agente = mensajeAgenteVacio()
    setMensajes([...lista, agente].slice(-MAX_MENSAJES_GUARDADOS))
    transmitir(lista, agente.id)
  }, [fase, mensajes, transmitir])

  // Detener deja lo que ya llegó, marcado como incompleto
  const detener = useCallback(() => {
    if (!control.current && fase !== 'espera') return
    cancelar()
    setMensajes(lista => lista.map((m, i) => (
      i === lista.length - 1 && m.rol === 'agente' && !m.terminado ? { ...m, incompleto: true, detenido: true } : m
    )))
    setError(null)
    setFase('reposo')
  }, [cancelar, fase])

  const nuevaConversacion = useCallback(() => {
    cancelar()
    setMensajes([])
    setError(null)
    setFase('reposo')
  }, [cancelar])

  return {
    mensajes, fase, error, esperaS, demorado,
    ocupado: ['enviando', 'transmitiendo', 'espera'].includes(fase),
    enviar, reintentar, detener, nuevaConversacion,
  }
}
