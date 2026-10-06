import { useState } from 'react'
import { getAlertas, getAlertasResumen } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DistintivoBodega from '../components/DistintivoBodega'
import { AlertTriangle, XCircle, Clock, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react'
import { fmtConteo, fmtFecha, fmtNumero } from '../utils/formato'
import { BODEGA, TIPOS_ALERTA, URGENCIAS, etiquetaTipoAlerta } from '../utils/etiquetas'

// La API pagina (K2): se piden de a 50 en vez de las 4.452 del gerente (1,4 MB)
const POR_PAGINA = 50

const URGENCIA_STYLE = {
  critica: { bg: 'bg-red-50',    border: 'border-l-red-600',    icon: XCircle,       iconColor: 'text-red-600',    badge: 'bg-red-100 text-red-700' },
  alta:    { bg: 'bg-amber-50',  border: 'border-l-amber-500',  icon: AlertTriangle, iconColor: 'text-amber-600',  badge: 'bg-amber-100 text-amber-700' },
  media:   { bg: 'bg-blue-50',   border: 'border-l-blue-400',   icon: Clock,         iconColor: 'text-blue-500',   badge: 'bg-blue-100 text-blue-700' },
}

export default function Alertas() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()

  const [filtroTipo, setFiltroTipo] = useState('')
  const [filtroUrgencia, setFiltroUrgencia] = useState('')
  const [pagina, setPagina] = useState(1)

  // Cambiar un filtro vuelve a la primera página
  const filtrar = setter => valor => { setter(valor); setPagina(1) }

  const lista = useConsulta(
    op => getAlertas({
      tipo: filtroTipo || undefined, urgencia: filtroUrgencia || undefined, sucursalId, page: pagina, pageSize: POR_PAGINA,
    }, op),
    [filtroTipo, filtroUrgencia, sucursalId, pagina],
  )
  const resumen = useConsulta(op => getAlertasResumen(sucursalId, op), [sucursalId])

  const actualizar = () => {
    lista.recargar()
    resumen.recargar()
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Alertas</h2>
          {lista.datos && (
            <p className="text-xs text-slate-500">
              {fmtConteo(lista.datos.total, 'alerta activa', 'alertas activas')} · {fmtFecha(lista.datos.fecha_inventario)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {showSelector && (
            <SucursalSelector value={rawSucursalId} onChange={filtrar(setSucursalId)} />
          )}
          <button
            onClick={actualizar}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-brand-blue border border-brand-blue rounded-lg hover:bg-blue-50"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Actualizar
          </button>
        </div>
      </div>

      <EstadoConsulta consulta={resumen} alto="h-20">
        {r => <Resumen global_={r.global_} />}
      </EstadoConsulta>

      <div className="flex flex-wrap gap-2">
        <select aria-label="Tipo" value={filtroTipo} onChange={e => filtrar(setFiltroTipo)(e.target.value)}
          className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden">
          <option value="">Todos los tipos</option>
          {Object.entries(TIPOS_ALERTA).map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>{etiqueta}</option>
          ))}
        </select>
        <select aria-label="Urgencia" value={filtroUrgencia} onChange={e => filtrar(setFiltroUrgencia)(e.target.value)}
          className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden">
          <option value="">Todas las urgencias</option>
          {Object.entries(URGENCIAS).map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>{etiqueta}</option>
          ))}
        </select>
      </div>

      <EstadoConsulta consulta={lista}>
        {d => <Lista datos={d} setPagina={setPagina} />}
      </EstadoConsulta>
    </div>
  )
}

function Resumen({ global_ }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="bg-white p-3 rounded-xl shadow-xs border border-slate-100 text-center">
        <p className="text-2xl font-bold text-slate-800">{fmtNumero(global_.total)}</p>
        <p className="text-xs text-slate-500 font-medium">Total</p>
      </div>
      <div className="bg-red-50 p-3 rounded-xl border border-red-100 text-center">
        <p className="text-2xl font-bold text-red-900">{fmtNumero(global_.critica)}</p>
        <p className="text-xs text-red-600 font-semibold">Críticas</p>
      </div>
      <div className="bg-amber-50 p-3 rounded-xl border border-amber-100 text-center">
        <p className="text-2xl font-bold text-amber-900">{fmtNumero(global_.alta)}</p>
        <p className="text-xs text-amber-600 font-semibold">Altas</p>
      </div>
      <div className="bg-blue-50 p-3 rounded-xl border border-blue-100 text-center">
        <p className="text-2xl font-bold text-blue-900">{fmtNumero(global_.media)}</p>
        <p className="text-xs text-blue-600 font-semibold">Medias</p>
      </div>
    </div>
  )
}

function Lista({ datos, setPagina }) {
  const { items, total, page: actual, pages: paginas } = datos
  if (!items.length) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
        <p className="text-green-800 font-semibold">Sin alertas</p>
        <p className="text-green-600 text-sm mt-1">No hay alertas que coincidan con los filtros seleccionados.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {items.map(alerta => {
        const style = URGENCIA_STYLE[alerta.urgencia] || URGENCIA_STYLE.media
        const Icon = style.icon
        return (
          <div key={`${alerta.tipo}-${alerta.id_producto}-${alerta.id_sucursal}`}
            className={`${style.bg} border-l-4 ${style.border} rounded-r-lg p-3 flex items-start gap-3 shadow-xs`}>
            <div className={`p-1.5 rounded-md ${style.iconColor}`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-bold text-slate-800">{alerta.nombre_producto}</p>
                  <p className="text-xs text-slate-500">
                    {alerta.sucursal}{alerta.tipo_ubicacion === BODEGA && <DistintivoBodega />} · {etiquetaTipoAlerta(alerta.tipo)}
                  </p>
                </div>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${style.badge}`}>
                  {URGENCIAS[alerta.urgencia] ?? alerta.urgencia}
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1">{alerta.detalle}</p>
            </div>
          </div>
        )
      })}

      {paginas > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-slate-500">
            Página {actual} de {paginas} · {fmtNumero(total)} alertas
          </p>
          <div className="flex gap-1">
            <button aria-label="Página anterior" onClick={() => setPagina(Math.max(1, actual - 1))} disabled={actual === 1}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button aria-label="Página siguiente" onClick={() => setPagina(Math.min(paginas, actual + 1))}
              disabled={actual >= paginas}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
