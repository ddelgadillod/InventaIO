import { useState, useEffect } from 'react'
import { getAlertas, getAlertasResumen } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import SucursalSelector from '../components/SucursalSelector'
import { Loader2, AlertTriangle, XCircle, Clock, RotateCcw } from 'lucide-react'

const URGENCIA_STYLE = {
  critica: { bg: 'bg-red-50',    border: 'border-l-red-600',    icon: XCircle,       iconColor: 'text-red-600',    badge: 'bg-red-100 text-red-700' },
  alta:    { bg: 'bg-amber-50',  border: 'border-l-amber-500',  icon: AlertTriangle, iconColor: 'text-amber-600',  badge: 'bg-amber-100 text-amber-700' },
  media:   { bg: 'bg-blue-50',   border: 'border-l-blue-400',   icon: Clock,         iconColor: 'text-blue-500',   badge: 'bg-blue-100 text-blue-700' },
}

const TIPO_LABEL = {
  stock_critico:  'Stock crítico',
  stock_bajo:     'Stock bajo',
  sin_movimiento: 'Sin movimiento',
  rotacion_baja:  'Rotación baja',
}

export default function Alertas() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()

  const [alertas, setAlertas] = useState(null)
  const [resumen, setResumen] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filtroTipo, setFiltroTipo] = useState('')
  const [filtroUrgencia, setFiltroUrgencia] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([
      getAlertas(filtroTipo || undefined, filtroUrgencia || undefined, sucursalId).then(setAlertas),
      getAlertasResumen(sucursalId).then(setResumen),
    ])
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [filtroTipo, filtroUrgencia, sucursalId])

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Alertas</h2>
          {alertas && <p className="text-xs text-slate-500">{alertas.total} alertas activas · {alertas.fecha_inventario}</p>}
        </div>
        <div className="flex items-center gap-2">
          {showSelector && (
            <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />
          )}
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-brand-blue border border-brand-blue rounded-lg hover:bg-blue-50">
            <RotateCcw className="w-3.5 h-3.5" /> Actualizar
          </button>
        </div>
      </div>

      {/* Resumen cards */}
      {resumen && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white p-3 rounded-xl shadow-sm border border-slate-100 text-center">
            <p className="text-2xl font-bold text-slate-800">{resumen.global_.total}</p>
            <p className="text-xs text-slate-500 font-medium">Total</p>
          </div>
          <div className="bg-red-50 p-3 rounded-xl border border-red-100 text-center">
            <p className="text-2xl font-bold text-red-900">{resumen.global_.critica}</p>
            <p className="text-xs text-red-600 font-semibold">Críticas</p>
          </div>
          <div className="bg-amber-50 p-3 rounded-xl border border-amber-100 text-center">
            <p className="text-2xl font-bold text-amber-900">{resumen.global_.alta}</p>
            <p className="text-xs text-amber-600 font-semibold">Altas</p>
          </div>
          <div className="bg-blue-50 p-3 rounded-xl border border-blue-100 text-center">
            <p className="text-2xl font-bold text-blue-900">{resumen.global_.media}</p>
            <p className="text-xs text-blue-600 font-semibold">Medias</p>
          </div>
        </div>
      )}

      {/* Filtros */}
      <div className="flex flex-wrap gap-2">
        <select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}
          className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-none">
          <option value="">Todos los tipos</option>
          <option value="stock_critico">Stock crítico</option>
          <option value="stock_bajo">Stock bajo</option>
          <option value="sin_movimiento">Sin movimiento</option>
          <option value="rotacion_baja">Rotación baja</option>
        </select>
        <select value={filtroUrgencia} onChange={e => setFiltroUrgencia(e.target.value)}
          className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-none">
          <option value="">Todas las urgencias</option>
          <option value="critica">Crítica</option>
          <option value="alta">Alta</option>
          <option value="media">Media</option>
        </select>
      </div>

      {/* Lista de alertas */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-6 h-6 animate-spin text-brand-blue" />
        </div>
      ) : alertas?.items?.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
          <p className="text-green-800 font-semibold">Sin alertas</p>
          <p className="text-green-600 text-sm mt-1">No hay alertas que coincidan con los filtros seleccionados.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alertas?.items?.map((alerta, i) => {
            const style = URGENCIA_STYLE[alerta.urgencia] || URGENCIA_STYLE.media
            const Icon = style.icon
            return (
              <div key={i} className={`${style.bg} border-l-4 ${style.border} rounded-r-lg p-3 flex items-start gap-3 shadow-sm`}>
                <div className={`p-1.5 rounded-md ${style.iconColor}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-slate-800">{alerta.nombre_producto}</p>
                      <p className="text-xs text-slate-500">{alerta.sucursal} · {TIPO_LABEL[alerta.tipo] || alerta.tipo}</p>
                    </div>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${style.badge}`}>
                      {alerta.urgencia}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{alerta.detalle}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
