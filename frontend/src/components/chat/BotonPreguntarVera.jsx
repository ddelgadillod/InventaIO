import Vera from './Vera'
import { usePreguntarAVera } from '../../hooks/useChatPanel'

// «Preguntar a Vera» desde una página (M7): solo el ícono de Vera (identidad vera-v2), con la
// pregunta en el nombre accesible y en el tooltip. Abre Vera con la pregunta ya enviada
export default function BotonPreguntarVera({ pregunta, className = '' }) {
  const preguntar = usePreguntarAVera()
  if (!preguntar) return null
  const nombre = `Preguntar a Vera: ${pregunta}`
  return (
    <button
      type="button"
      onClick={() => preguntar(pregunta)}
      aria-label={nombre}
      title={nombre}
      className={`p-1 rounded-lg hover:bg-white/80 hover:shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue ${className}`}
    >
      <Vera variante="icono" className="w-6 h-6" titulo="" />
    </button>
  )
}
