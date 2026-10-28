/**
 * InventAI/o — Lógica pura del chat (INV-35)
 * Cómo un evento del agente va armando su mensaje, qué historial se envía y
 * cómo se explica cada error. Sin React: el estado lo lleva hooks/useChat.js.
 */
import { MAX_CARACTERES_MENSAJE, MAX_MENSAJES } from '../api/chat'

// Tope del cuerpo que acepta el Core API
const MAX_CARACTERES_TOTAL = 16_000
// Lo que guarda el panel: más que lo que ve el agente (Y4)
export const MAX_MENSAJES_GUARDADOS = 40
export const TURNOS_QUE_RECUERDA_EL_AGENTE = Math.floor(MAX_MENSAJES / 2)

let contador = 0
export const nuevoId = () => `m${Date.now().toString(36)}${(contador++).toString(36)}`

export const mensajeUsuario = texto => ({ id: nuevoId(), rol: 'usuario', texto })

// El mensaje del agente nace vacío y se llena con los eventos del flujo
export const mensajeAgenteVacio = () => ({
  id: nuevoId(),
  rol: 'agente',
  texto: '',
  modelo: null,
  herramientas: [],
  datos: [],
  fechasDatos: [],
  sugerencias: [],
  respaldo: false,
  fidelidad: null,
  msTotal: null,
  turnosRecortados: 0,
  terminado: false,
  error: null,
})

/** Aplica un evento { evento, datos } a un mensaje del agente y devuelve el nuevo. */
export function aplicarEvento(msg, { evento, datos }) {
  switch (evento) {
    case 'meta':
      return { ...msg, modelo: datos.modelo ?? null }
    case 'tool': {
      const existe = msg.herramientas.some(h => h.id === datos.id)
      const herramienta = {
        id: datos.id,
        nombre: datos.nombre,
        estado: datos.estado,
        lenta: Boolean(datos.lenta),
        ms: datos.ms ?? null,
        codigo: datos.codigo ?? null,
      }
      return {
        ...msg,
        herramientas: existe
          // La etiqueta solo viene en `inicio`: al cerrar se conserva
          ? msg.herramientas.map(h => (h.id === datos.id
            ? { ...h, ...herramienta, etiqueta: datos.etiqueta ?? h.etiqueta, lenta: h.lenta || herramienta.lenta }
            : h))
          : [...msg.herramientas, { ...herramienta, etiqueta: datos.etiqueta ?? datos.nombre }],
      }
    }
    case 'data':
      return { ...msg, datos: [...msg.datos, datos] }
    case 'token':
      return { ...msg, texto: msg.texto + (datos.texto ?? '') }
    case 'done':
      return {
        ...msg,
        terminado: true,
        sugerencias: Array.isArray(datos.sugerencias) ? datos.sugerencias.slice(0, 3) : [],
        respaldo: Boolean(datos.respaldo),
        fidelidad: datos.fidelidad ?? null,
        fechasDatos: Array.isArray(datos.fechas_datos) ? datos.fechas_datos : [],
        msTotal: datos.ms_total ?? null,
        turnosRecortados: datos.turnos_recortados ?? 0,
      }
    case 'error':
      return { ...msg, error: { codigo: datos.codigo, mensaje: datos.mensaje ?? '' } }
    default:
      return msg
  }
}

/**
 * Etapa visible mientras Vera trabaja: conectando (sin `meta`), analizando (eligiendo
 * herramienta), consultando, verificando (ya consultó y aún no redacta) o redactando.
 */
export function etapaDe(msg) {
  if (!msg) return null
  if (msg.texto) return 'redactando'
  if (msg.herramientas.some(h => h.estado === 'inicio')) return 'consultando'
  if (msg.herramientas.length || msg.datos.length) return 'verificando'
  return msg.modelo ? 'analizando' : 'conectando'
}

/**
 * Historial que se envía al agente: solo las preguntas que tuvieron respuesta
 * completa (con su respuesta) y la pregunta nueva al final. Se recorta a lo que
 * acepta el Core API: 13 mensajes y 16.000 caracteres, siempre desde el más viejo.
 */
export function historialParaEnviar(mensajes) {
  const salida = []
  for (let i = 0; i < mensajes.length; i++) {
    const m = mensajes[i]
    const siguiente = mensajes[i + 1]
    if (m.rol === 'usuario') {
      if (i === mensajes.length - 1) salida.push({ rol: 'usuario', texto: m.texto })
      else if (siguiente?.rol === 'agente' && siguiente.terminado && !siguiente.respaldo && siguiente.texto) {
        salida.push({ rol: 'usuario', texto: m.texto }, { rol: 'agente', texto: siguiente.texto })
      }
    }
  }
  const acotados = salida.map(m => ({ ...m, texto: m.texto.slice(0, MAX_CARACTERES_MENSAJE) }))
  let recorte = acotados.slice(-MAX_MENSAJES)
  const total = lista => lista.reduce((suma, m) => suma + m.texto.length, 0)
  // Siempre se empieza por una pregunta, y se suelta de a un turno
  while (recorte.length > 1 && (recorte[0].rol !== 'usuario' || total(recorte) > MAX_CARACTERES_TOTAL)) {
    recorte = recorte.slice(recorte[0].rol === 'usuario' && recorte[1]?.rol === 'agente' ? 2 : 1)
  }
  return recorte
}

/** ¿Se está olvidando algo de la conversación? (Y4) */
export function seRecortaLaConversacion(mensajes) {
  const completos = mensajes.filter(m => m.rol === 'usuario').length
  return completos > TURNOS_QUE_RECUERDA_EL_AGENTE
}

/**
 * Qué le pasó a la consulta, en palabras de usuario. Acepta un ApiError del
 * cliente o el evento `error` del flujo ({ codigo, mensaje }).
 * Devuelve { titulo, detalle, reintentable }.
 */
export function describirError(error) {
  if (!error) return null
  if (error.codigo) {
    const porCodigo = {
      llm_no_disponible: ['Vera no está disponible', 'El modelo no respondió. Intenta de nuevo en un momento.', true],
      modelo_no_descargado: ['Vera no está disponible', 'El modelo todavía no está instalado en el servidor.', false],
      solicitud_invalida: ['No se pudo enviar la pregunta', 'La conversación no cumple los límites del chat. Empieza una nueva.', false],
      respuesta_invalida: ['Vera dio una respuesta inválida', 'Intenta de nuevo o reformula la pregunta.', true],
      tiempo_agotado: ['La consulta tardó demasiado', 'Pasaron más de 120 s sin respuesta completa. Intenta con una pregunta más acotada.', true],
    }
    const [titulo, detalle, reintentable] = porCodigo[error.codigo]
      ?? ['Algo falló en Vera', error.mensaje || 'Intenta de nuevo.', true]
    return { titulo, detalle, reintentable }
  }
  const { status } = error
  if (error.cancelada) return null
  if (status === 401) return { titulo: 'Tu sesión expiró', detalle: 'Vuelve a iniciar sesión para seguir.', reintentable: false }
  if (status === 403) return { titulo: 'No tienes permiso', detalle: 'Tu rol no puede hacer esta consulta.', reintentable: false }
  if (status === 422) {
    return { titulo: 'No se pudo enviar la pregunta', detalle: error.detail || 'La pregunta no cumple los límites del chat.', reintentable: false }
  }
  if (status === 429) {
    return { titulo: 'Vera está atendiendo otra consulta', detalle: 'Se reintentará en un momento.', reintentable: true }
  }
  if (status === 0) return { titulo: 'Sin conexión con el servidor', detalle: error.detail || 'Revisa tu conexión.', reintentable: true }
  return { titulo: 'Vera no está disponible', detalle: 'El servicio no respondió a tiempo. Intenta de nuevo en un momento.', reintentable: true }
}

/** Herramientas que no devolvieron datos por permisos (403 dentro del flujo). */
export const hayHerramientaDenegada = msg => msg.herramientas.some(h => h.codigo === 403)

// Por qué Vera no está disponible al abrirla (M3): el `motivo` de /api/chat/health
const MOTIVOS = {
  ollama_no_alcanzable: 'El modelo de lenguaje no está encendido.',
  modelo_no_descargado: 'El modelo de lenguaje no está instalado en el servidor.',
  agente_no_disponible: 'El servicio de Vera no responde.',
  sin_conexion: 'No hay conexión con el servidor.',
}
export const describirSalud = motivo => MOTIVOS[motivo] ?? MOTIVOS.agente_no_disponible
