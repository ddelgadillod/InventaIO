import { useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { textoPlano } from '../../utils/markdown'

const AVISO_MS = 2000

// Copiar la respuesta de Vera sin marcas de Markdown (M9). Sin portapapeles (un sitio sin
// HTTPS fuera de localhost) no se muestra
export default function BotonCopiar({ texto }) {
  const [copiada, setCopiada] = useState(false)
  useEffect(() => {
    if (!copiada) return undefined
    const t = setTimeout(() => setCopiada(false), AVISO_MS)
    return () => clearTimeout(t)
  }, [copiada])
  if (!navigator.clipboard?.writeText) return null
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(textoPlano(texto))
      setCopiada(true)
    } catch { /* el navegador lo negó: no hay nada que avisar */ }
  }
  return (
    <button type="button" onClick={copiar}
      className="inline-flex items-center gap-1 shrink-0 px-1.5 py-0.5 rounded text-slate-500 hover:text-brand-blue hover:bg-blue-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue">
      {copiada ? <Check className="w-3.5 h-3.5" aria-hidden="true" /> : <Copy className="w-3.5 h-3.5" aria-hidden="true" />}
      <span aria-live="polite">{copiada ? 'Copiada' : 'Copiar'}</span>
    </button>
  )
}
