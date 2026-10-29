import { ChevronRight, Download } from 'lucide-react'
import { descargarCSV } from '../../utils/csv'
import { nombreCSV, tablaACSV } from '../../utils/tablaVera'

// Evento `data` del agente (contrato v1.1): los valores llegan ya formateados en es-CO,
// como texto, con la unidad incluida. Se muestran tal cual, sin formatear de nuevo (C7).
// La fecha del dato va una sola vez, al pie de la respuesta (MensajeChat).
// Con varias tablas, solo la primera llega abierta: el resto se despliega por su título.
// Las cifras (`numero` y `cantidad`) van a la derecha; el CSV las lleva como números (M4)
const NUMERICA = new Set(['numero', 'cantidad'])

export default function TablaDatos({ datos, abierta = true }) {
  const { titulo, columnas = [], filas = [], total, mostrando } = datos
  const faltan = typeof total === 'number' && typeof mostrando === 'number' && total > mostrando
  const nombre = titulo || 'Datos consultados'
  return (
    <details open={abierta} className="group mt-2 rounded-lg border border-slate-200 bg-white overflow-hidden">
      <summary className="flex items-center gap-1 cursor-pointer list-none px-3 py-1.5 text-xs font-semibold text-brand-navy bg-slate-50 border-b border-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue">
        <ChevronRight className="w-3.5 h-3.5 shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
        {nombre}
      </summary>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-600">
              {columnas.map(c => (
                <th key={c.clave} scope="col" className={`px-3 py-1.5 font-semibold whitespace-nowrap ${NUMERICA.has(c.tipo) ? 'text-right' : 'text-left'}`}>{c.titulo}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, i) => (
              <tr key={i} className="border-t border-slate-100">
                {columnas.map(c => (
                  <td key={c.clave} className={`px-3 py-1.5 text-slate-700 ${NUMERICA.has(c.tipo) ? 'text-right tabular-nums whitespace-nowrap' : 'min-w-[8rem]'}`}>{fila[c.clave] ?? '—'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-2 px-3 py-1 text-[11px] text-slate-500 border-t border-slate-100">
        <span>{faltan && `Se muestran ${mostrando} de ${total}.`}</span>
        <button
          type="button"
          onClick={() => descargarCSV(nombreCSV(titulo), tablaACSV(datos))}
          aria-label={`Descargar ${nombre} en CSV`}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-brand-blue hover:bg-blue-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue"
        >
          <Download className="w-3.5 h-3.5" aria-hidden="true" /> CSV
        </button>
      </div>
    </details>
  )
}
