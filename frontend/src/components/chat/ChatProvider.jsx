import { useCallback, useMemo, useState } from 'react'
import useChat from '../../hooks/useChat'
import useMedia from '../../hooks/useMedia'
import { CONSULTA_VENTANA, ChatContext } from '../../hooks/useChatPanel'

// La conversación vive aquí, en AppShell, y no en el panel: así sobrevive al cambio de
// ruta y a cerrar el panel (CA 1). Solo se pierde al recargar o con «Nueva conversación».
// `modal`: Vera tapa la página (maximizada, o en pantallas angostas) y lo de atrás queda inert
export default function ChatProvider({ children }) {
  const chat = useChat()
  const flotante = useMedia(CONSULTA_VENTANA)
  const [abierto, setAbierto] = useState(false)
  const [maximizado, setMaximizado] = useState(false)
  const abrir = useCallback(() => setAbierto(true), [])
  const cerrar = useCallback(() => setAbierto(false), [])
  const alternarMaximizado = useCallback(() => setMaximizado(m => !m), [])
  // Desde una página (M7): abre Vera y envía la pregunta; con otra respuesta en curso, solo la abre
  const { enviar } = chat
  const preguntar = useCallback((texto) => {
    setAbierto(true)
    enviar(texto)
  }, [enviar])
  const modal = abierto && (!flotante || maximizado)
  const valor = useMemo(
    () => ({ ...chat, abierto, abrir, cerrar, flotante, maximizado, alternarMaximizado, modal, preguntar }),
    [chat, abierto, abrir, cerrar, flotante, maximizado, alternarMaximizado, modal, preguntar],
  )
  return <ChatContext.Provider value={valor}>{children}</ChatContext.Provider>
}
