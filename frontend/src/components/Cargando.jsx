import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

/**
 * Spinner de carga (INV-26 fix, A2.11). Con `aviso`, lo muestra pasados
 * `avisoTrasMs` (para las consultas de ML que tardan hasta 40 s en frío).
 */
export default function Cargando({ aviso, avisoTrasMs = 5000, alto = 'h-48' }) {
  const [mostrarAviso, setMostrarAviso] = useState(false)

  useEffect(() => {
    if (!aviso) return undefined
    const t = setTimeout(() => setMostrarAviso(true), avisoTrasMs)
    return () => clearTimeout(t)
  }, [aviso, avisoTrasMs])

  return (
    <div role="status" className={`flex flex-col items-center justify-center gap-2 ${alto}`}>
      <Loader2 className="w-6 h-6 animate-spin text-brand-blue" />
      {mostrarAviso && <p className="text-xs text-slate-500">{aviso}</p>}
      <span className="sr-only">Cargando</span>
    </div>
  )
}
