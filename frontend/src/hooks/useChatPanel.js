import { createContext, useContext } from 'react'

// Contexto de Vera (INV-35): lo llena ChatProvider, en AppShell
export const ChatContext = createContext(null)

// id del botón flotante: el panel le devuelve el foco al cerrarse
export const ID_BOTON_VERA = 'boton-vera'

// Desde sm (40rem) Vera es una ventana flotante que se puede maximizar; más angosto,
// ocupa toda la pantalla
export const CONSULTA_VENTANA = '(min-width: 40rem)'

// Para las páginas (M7): abre Vera y le pregunta. Fuera de ChatProvider (las pruebas
// de cada página) devuelve null y el botón no se muestra
export function usePreguntarAVera() {
  return useContext(ChatContext)?.preguntar ?? null
}

export default function useChatPanel() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChatPanel must be inside ChatProvider')
  return ctx
}
