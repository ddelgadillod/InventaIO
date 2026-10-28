import Vera from './Vera'
import useChatPanel, { ID_BOTON_VERA } from '../../hooks/useChatPanel'

// Botón flotante: el ícono de Vera sobre el azul marino; con el panel abierto se oculta
export default function BotonChat() {
  const { abierto, abrir, ocupado } = useChatPanel()
  if (abierto) return null
  return (
    <button
      id={ID_BOTON_VERA}
      type="button"
      onClick={abrir}
      aria-label="Abrir el chat con Vera"
      className="fixed bottom-5 right-5 z-30 w-14 h-14 rounded-full bg-brand-navy hover:bg-brand-navydark active:bg-brand-navydark shadow-lg flex items-center justify-center focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-blue/40"
    >
      <Vera variante="icono-oscuro" pensando={ocupado} className="w-9 h-9" titulo="" />
    </button>
  )
}
