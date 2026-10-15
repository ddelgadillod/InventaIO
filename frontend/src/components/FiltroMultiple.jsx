import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

/**
 * Filtro desplegable con casillas para elegir varios valores (INV-28, V13).
 * Sin ninguno marcado equivale a "todos". El botón resume la selección:
 * `vacio`, el nombre del único valor o "N <plural>".
 *
 *   <FiltroMultiple etiqueta="Tipo" vacio="Todos los tipos" plural="tipos"
 *     opciones={TIPOS_ALERTA} valores={tipos} onChange={setTipos} />
 */
export default function FiltroMultiple({ etiqueta, vacio, plural, opciones, valores, onChange }) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef(null)

  // Se cierra con un clic fuera o con Escape
  useEffect(() => {
    if (!abierto) return undefined
    const fuera = e => { if (!caja.current?.contains(e.target)) setAbierto(false) }
    const escape = e => { if (e.key === 'Escape') setAbierto(false) }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('keydown', escape)
    }
  }, [abierto])

  const resumen = valores.length === 0 ? vacio
    : valores.length === 1 ? (opciones[valores[0]] ?? valores[0])
      : `${valores.length} ${plural}`

  // Conserva el orden de las opciones, no el de los clics
  const alternar = valor => onChange(valores.includes(valor)
    ? valores.filter(v => v !== valor)
    : Object.keys(opciones).filter(v => v === valor || valores.includes(v)))

  return (
    <div ref={caja} className="relative">
      <button type="button" aria-haspopup="true" aria-expanded={abierto} aria-label={`${etiqueta}: ${resumen}`}
        onClick={() => setAbierto(a => !a)}
        className={`h-9 px-3 text-xs rounded-lg border bg-white flex items-center gap-2 whitespace-nowrap ${valores.length
          ? 'border-brand-blue text-brand-blue font-semibold' : 'border-slate-200 text-slate-700'}`}>
        {resumen}
        <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
      {abierto && (
        <div role="group" aria-label={etiqueta}
          className="absolute z-20 mt-1 min-w-full w-max bg-white border border-slate-200 rounded-lg shadow-lg p-1.5">
          {Object.entries(opciones).map(([valor, texto]) => (
            <label key={valor}
              className="flex items-center gap-2 px-2 py-1.5 text-xs text-slate-700 rounded-md hover:bg-slate-50 whitespace-nowrap cursor-pointer">
              <input type="checkbox" checked={valores.includes(valor)} onChange={() => alternar(valor)}
                className="w-3.5 h-3.5 accent-brand-blue" />
              {texto}
            </label>
          ))}
          {valores.length > 0 && (
            <button type="button" onClick={() => onChange([])}
              className="w-full text-left px-2 py-1.5 mt-1 border-t border-slate-100 text-xs text-brand-blue hover:underline">
              {vacio}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
