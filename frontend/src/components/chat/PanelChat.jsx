import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AlertCircle, Maximize2, Minimize2, Plus, RotateCcw, SendHorizontal, Square, X } from 'lucide-react'
import { MensajeUsuario, MensajeVera } from './MensajeChat'
import Vera from './Vera'
import useChatPanel, { ID_BOTON_VERA, ID_CAMPO_VERA, ID_VENTANA_VERA } from '../../hooks/useChatPanel'
import { useLocation } from 'react-router'
import { useAuth } from '../../api/AuthContext'
import { MAX_CARACTERES_MENSAJE, saludVera } from '../../api/chat'
import { useConsulta } from '../../hooks/useConsulta'
import { TURNOS_QUE_RECUERDA_EL_AGENTE, describirSalud, etapaDe, seRecortaLaConversacion } from '../../utils/chat'
import { preguntasRapidas } from '../../utils/preguntasRapidas'

// Distancia al final (px) bajo la cual la lista sigue lo que va llegando
const PEGADO_AL_FINAL_PX = 48

// Lo que se le dice al usuario mientras no llega texto: conectando, consultando o verificando
function textoDeEstado({ fase, esperaS }, ultimo) {
  if (fase === 'espera') return `Vera está atendiendo otra consulta. Reintentando${esperaS ? ` en ${esperaS} s` : ''}…`
  if (fase === 'enviando') return 'Conectando con Vera…'
  if (fase !== 'transmitiendo') return null
  const etapa = etapaDe(ultimo)
  if (etapa === 'redactando') return null
  const activas = ultimo.herramientas.filter(h => h.estado === 'inicio')
  if (etapa === 'consultando') {
    if (activas.some(h => h.lenta)) return 'Calculando recomendaciones… puede tardar hasta 40 s'
    return `Consultando ${activas.map(h => h.etiqueta).join(', ')}…`
  }
  if (etapa === 'verificando') return 'Verificando la respuesta…'
  return etapa === 'analizando' ? 'Analizando tu pregunta…' : 'Conectando con Vera…'
}

function Botones({ textos, deshabilitado, onElegir, etiqueta }) {
  if (!textos.length) return null
  return (
    <div role="group" aria-label={etiqueta} className="flex flex-wrap gap-2">
      {textos.map(t => (
        <button
          key={t}
          type="button"
          disabled={deshabilitado}
          onClick={() => onElegir(t)}
          className="text-left text-xs px-3 py-1.5 rounded-full border border-brand-blue/40 text-brand-blue bg-white hover:bg-blue-50 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue"
        >
          {t}
        </button>
      ))}
    </div>
  )
}

export default function PanelChat() {
  const chat = useChatPanel()
  const { user } = useAuth()
  const { pathname } = useLocation()
  const {
    mensajes, fase, error, ocupado, enviar, detener, reintentar, nuevaConversacion, cerrar,
    maximizado, alternarMaximizado, modal, demorado,
  } = chat
  const [texto, setTexto] = useState('')
  const campo = useRef(null)
  const lista = useRef(null)
  const pegado = useRef(true)
  // M3: cada vez que se abre, ¿Vera puede responder? Mientras se averigua, no se bloquea
  const salud = useConsulta(op => saludVera(op), [])
  const noDisponible = salud.datos?.listo === false

  // Foco en el campo al abrir; al cerrar, de vuelta en el botón flotante
  useEffect(() => {
    campo.current?.focus()
    return () => document.getElementById(ID_BOTON_VERA)?.focus()
  }, [])

  // Solo se desplaza la lista, y solo si el usuario no subió a leer algo anterior.
  // scrollIntoView movía también los contenedores de afuera (la página entera)
  useEffect(() => {
    const l = lista.current
    if (l && pegado.current) l.scrollTop = l.scrollHeight
  }, [mensajes, fase, error, maximizado])
  // M10: el campo crece con el texto, de 2 a 6 líneas (max-h-36); después se desplaza
  useLayoutEffect(() => {
    const c = campo.current
    if (!c) return
    c.style.height = 'auto'
    if (c.scrollHeight) c.style.height = `${c.scrollHeight}px`
  }, [texto])

  const alDesplazar = () => {
    const l = lista.current
    pegado.current = l.scrollHeight - l.scrollTop - l.clientHeight < PEGADO_AL_FINAL_PX
  }

  const ultimo = mensajes[mensajes.length - 1]
  const ultimoVera = ultimo?.rol === 'agente' ? ultimo : null
  const estado = textoDeEstado(chat, ultimoVera ?? { herramientas: [], datos: [], texto: '' })
  // M2: sin eventos hace 10 s y sin texto todavía; la herramienta lenta ya trae su propio aviso
  const avisoDemora = demorado && estado && fase !== 'espera' && !estado.startsWith('Calculando recomendaciones')
  const sugerencias = !ocupado && ultimoVera?.terminado ? ultimoVera.sugerencias : []
  // M12: las de la página en que está el usuario; en el Dashboard, las de su rol
  const rapidas = preguntasRapidas(user?.rol, pathname)

  // La pregunta rápida o la sugerencia que se pulsa desaparece: el foco vuelve al campo
  const mandar = (t) => {
    if (!noDisponible && enviar(t)) {
      setTexto('')
      pegado.current = true
    }
    campo.current?.focus()
  }
  const alTeclear = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      mandar(texto)
    }
  }
  const alPulsarEscape = (e) => { if (e.key === 'Escape') cerrar() }

  // Pantalla completa en el celular; desde sm, ventana flotante abajo a la derecha que no
  // tapa la página, o maximizada sobre un fondo oscuro. El contenido maximizado va en una
  // columna legible
  const ventana = maximizado
    ? 'sm:inset-4 lg:inset-6 sm:rounded-2xl'
    : 'sm:inset-auto sm:bottom-4 sm:right-4 sm:w-[26rem] sm:h-[min(44rem,calc(100dvh-2rem))] sm:rounded-2xl'
  const columna = maximizado ? 'sm:max-w-4xl sm:mx-auto' : ''

  return (
    <>
      {modal && maximizado && (
        <div className="hidden sm:block fixed inset-0 z-40 bg-slate-900/40" aria-hidden="true" onClick={alternarMaximizado} />
      )}
      <section
        id={ID_VENTANA_VERA}
        role="dialog"
        aria-modal={modal}
        aria-label="Chat con Vera"
        onKeyDown={alPulsarEscape}
        className={`fixed inset-0 z-50 flex flex-col bg-white overflow-hidden sm:border sm:border-slate-200 sm:shadow-2xl ${ventana}`}
      >
        <header className="bg-brand-navy text-white px-4 py-3 flex items-center gap-3 shrink-0">
          <Vera variante="icono-oscuro" pensando={ocupado} className="w-9 h-9 shrink-0" titulo="" />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-bold leading-tight">Vera</h2>
            <p className="text-xs text-white/70 truncate">Pregúntale a tu inventario</p>
          </div>
          <button type="button" onClick={() => { nuevaConversacion(); campo.current?.focus() }} disabled={!mensajes.length && !error}
            aria-label="Nueva conversación" title="Nueva conversación"
            className="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-white">
            <Plus className="w-5 h-5" aria-hidden="true" />
          </button>
          <button type="button" onClick={alternarMaximizado}
            aria-label={maximizado ? 'Restaurar el tamaño' : 'Maximizar'} title={maximizado ? 'Restaurar el tamaño' : 'Maximizar'}
            className="hidden sm:inline-flex p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-white">
            {maximizado ? <Minimize2 className="w-5 h-5" aria-hidden="true" /> : <Maximize2 className="w-5 h-5" aria-hidden="true" />}
          </button>
          <button type="button" onClick={cerrar} aria-label="Cerrar el chat"
            className="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-white">
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </header>

        {noDisponible && (
          <div role="alert" className="shrink-0 flex items-start gap-2 px-4 py-2.5 bg-red-50 border-b border-red-200 text-sm text-red-800">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <p className="font-semibold">Vera no está disponible</p>
              <p className="text-xs">{describirSalud(salud.datos.motivo)} Puedes escribir tu pregunta mientras tanto.</p>
            </div>
            <button type="button" onClick={salud.recargar} disabled={salud.cargando}
              className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-md bg-white border border-red-300 hover:bg-red-100 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
              <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" /> Volver a comprobar
            </button>
          </div>
        )}

        <div ref={lista} onScroll={alDesplazar} className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-4" role="log" aria-live="polite" aria-busy={ocupado} aria-label="Conversación con Vera">
          <div className={`space-y-3 ${columna}`}>
            {mensajes.length === 0 && (
              <div className="text-sm text-slate-600 space-y-3">
                <p><span className="font-semibold text-brand-navy">Hola, soy Vera</span>, la asistente de InventAI/o. Respondo con los datos de tu inventario, alertas, ventas y recomendaciones.</p>
                {rapidas.titulo && <p className="text-xs font-semibold text-slate-500">Sobre {rapidas.titulo}:</p>}
                <Botones textos={rapidas.preguntas} onElegir={mandar} deshabilitado={ocupado || noDisponible} etiqueta="Preguntas rápidas" />
              </div>
            )}
            {mensajes.map(m => (m.rol === 'usuario'
              ? <MensajeUsuario key={m.id} mensaje={m} />
              : <MensajeVera key={m.id} mensaje={m} />))}
            {estado && (
              <div role="status" className="flex items-start gap-2 text-xs text-slate-500">
                <Vera variante="avatar" pensando className="w-7 h-7 shrink-0" titulo="" />
                <div className="pt-1.5 space-y-1">
                  <p>{estado}</p>
                  {avisoDemora && (
                    <p className="text-slate-600">Está tardando más de lo normal: la primera pregunta después de iniciar el modelo puede tardar hasta un minuto.</p>
                  )}
                </div>
              </div>
            )}
            {error && (
              <div role="alert" className="ml-9 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                <p className="flex items-center gap-1.5 font-semibold"><AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />{error.titulo}</p>
                <p className="mt-0.5 text-xs">{error.detalle}</p>
                {error.reintentable && (
                  <button type="button" onClick={reintentar}
                    className="mt-2 inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-md bg-white border border-red-300 hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
                    <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" /> Reintentar
                  </button>
                )}
              </div>
            )}
            {sugerencias.length > 0 && (
              <div className="pl-9"><Botones textos={sugerencias} onElegir={mandar} deshabilitado={ocupado || noDisponible} etiqueta="Sugerencias de seguimiento" /></div>
            )}
          </div>
        </div>

        <form onSubmit={(e) => { e.preventDefault(); mandar(texto) }} className="border-t border-slate-200 p-3 shrink-0">
          <div className={columna}>
            {seRecortaLaConversacion(mensajes) && (
              <p className="text-[11px] text-slate-500 mb-1.5">Vera recuerda solo los últimos {TURNOS_QUE_RECUERDA_EL_AGENTE} turnos. Empieza una conversación nueva si cambias de tema.</p>
            )}
            <div className="flex items-end gap-2">
              <textarea
                ref={campo}
                id={ID_CAMPO_VERA}
                value={texto}
                onChange={e => setTexto(e.target.value)}
                onKeyDown={alTeclear}
                rows={2}
                maxLength={MAX_CARACTERES_MENSAJE}
                placeholder="Escribe tu pregunta…"
                aria-label="Escribe tu pregunta a Vera"
                className="flex-1 resize-none max-h-36 overflow-y-auto rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/30"
              />
              {ocupado ? (
                <button type="button" onClick={detener} aria-label="Detener la respuesta"
                  className="p-2.5 rounded-lg bg-slate-700 text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500">
                  <Square className="w-5 h-5" aria-hidden="true" />
                </button>
              ) : (
                <button type="submit" disabled={!texto.trim() || noDisponible} aria-label="Enviar pregunta"
                  className="p-2.5 rounded-lg bg-brand-blue text-white hover:bg-blue-700 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2">
                  <SendHorizontal className="w-5 h-5" aria-hidden="true" />
                </button>
              )}
            </div>
            <p className="mt-1 flex justify-between text-[11px] text-slate-500">
              <span>Enter envía · Mayús+Enter, nueva línea</span>
              {texto.length > MAX_CARACTERES_MENSAJE - 200 && <span>{texto.length}/{MAX_CARACTERES_MENSAJE}</span>}
            </p>
          </div>
        </form>
      </section>
    </>
  )
}
