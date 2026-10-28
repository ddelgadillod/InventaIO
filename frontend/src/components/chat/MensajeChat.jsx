import { Info, ShieldAlert } from 'lucide-react'
import Markdown from './Markdown'
import TablaDatos from './TablaDatos'
import BotonCopiar from './BotonCopiar'
import Vera from './Vera'
import { hayHerramientaDenegada } from '../../utils/chat'
import { fmtDecimal, fmtFecha } from '../../utils/formato'

export function MensajeUsuario({ mensaje }) {
  return (
    <div className="flex justify-end">
      {/* La esquina recta apunta a quien habla */}
      <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-blue text-white px-3.5 py-2 text-sm whitespace-pre-wrap break-words">
        <span className="sr-only">Tú: </span>{mensaje.texto}
      </p>
    </div>
  )
}

// Pie de la respuesta: qué se consultó (CA 6), la fecha del dato, cuánto tardó (M5) y copiar (M9)
function PieRespuesta({ mensaje }) {
  // Si el `done` no llegó (corte o detenida), la fecha sale de los `data` recibidos
  const fechas = mensaje.fechasDatos.length
    ? mensaje.fechasDatos
    : [...new Set(mensaje.datos.map(d => d.fecha_dato).filter(Boolean))]
  const tiempo = mensaje.msTotal !== null ? `Respondió en ${fmtDecimal(mensaje.msTotal / 1000, 1)} s` : null
  const copiable = mensaje.terminado && Boolean(mensaje.texto)
  if (!mensaje.herramientas.length && !tiempo && !copiable) return null
  return (
    <div className="mt-2 flex items-start justify-between gap-2 text-[11px] text-slate-500">
      <div className="space-y-0.5 min-w-0">
        {mensaje.herramientas.length > 0 && (
          <p>
            <span className="font-semibold">Consultado: </span>
            {mensaje.herramientas.map((h, i) => (
              <span key={h.id}>
                {i > 0 && ' · '}
                {h.etiqueta}
                {h.codigo === 403 && ' (sin permiso)'}
              </span>
            ))}
          </p>
        )}
        {(fechas.length > 0 || tiempo) && (
          <p>{[fechas.length > 0 && `Datos al ${fechas.map(fmtFecha).join(', ')}`, tiempo].filter(Boolean).join(' · ')}</p>
        )}
      </div>
      {copiable && <BotonCopiar texto={mensaje.texto} />}
    </div>
  )
}

// Mientras no hay nada que mostrar, el avatar «pensando» vive en la línea de estado del panel
export function MensajeVera({ mensaje }) {
  const conBurbuja = Boolean(mensaje.texto || mensaje.datos.length)
  if (!conBurbuja && !mensaje.herramientas.length) return null
  const denegada = hayHerramientaDenegada(mensaje)
  return (
    <div className="flex gap-2 items-start">
      {conBurbuja ? <Vera variante="avatar" className="w-7 h-7 shrink-0 mt-0.5" titulo="" /> : <span className="w-7 shrink-0" />}
      <div className="max-w-[88%] min-w-0">
        {conBurbuja && (
          <div className="rounded-2xl rounded-bl-sm bg-blue-50 text-slate-700 px-3.5 py-2 text-sm">
            <span className="sr-only">Vera: </span>
            {mensaje.respaldo && (
              <p className="flex items-center gap-1 mb-1 text-xs font-semibold text-slate-600">
                <Info className="w-3.5 h-3.5" aria-hidden="true" /> Respuesta de respaldo: Vera no pudo verificar su redacción
              </p>
            )}
            {denegada && (
              <p className="flex items-center gap-1 mb-1 text-xs font-semibold text-red-700">
                <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" /> Tu rol no tiene permiso para parte de esta consulta
              </p>
            )}
            {mensaje.texto && <Markdown texto={mensaje.texto} />}
            {mensaje.datos.map((d, i) => <TablaDatos key={d.id} datos={d} abierta={i === 0} />)}
            {mensaje.incompleto && (
              <p className="mt-1 text-xs italic text-slate-500">{mensaje.detenido ? 'Detenida.' : 'Respuesta incompleta.'}</p>
            )}
          </div>
        )}
        <PieRespuesta mensaje={mensaje} />
      </div>
    </div>
  )
}
