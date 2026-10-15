import { Sparkles } from 'lucide-react'

/** Marca lo que calcula el modelo de demanda (INV-28, V9), como la insignia de Predicciones. */
export default function DistintivoIA() {
  return (
    <span className="ml-1.5 inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] leading-4 font-bold rounded-sm bg-blue-100 text-brand-blue align-middle">
      <Sparkles className="w-3 h-3" aria-hidden="true" />IA
    </span>
  )
}
