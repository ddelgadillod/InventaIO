import { useState } from 'react'
import { getAlertas, getAlertasML, getAlertasResumen } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DistintivoBodega from '../components/DistintivoBodega'
import DistintivoIA from '../components/DistintivoIA'
import { AlertTriangle, XCircle, Clock, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react'
import { fmtConteo, fmtFecha, fmtNumero } from '../utils/formato'
import {
  BODEGA, ORIGENES_ALERTA_ML, TIPOS_ALERTA, TIPOS_ALERTA_ML, URGENCIAS, etiquetaTipoAlerta,
} from '../utils/etiquetas'

// La API pagina (K2): se piden de a 50 en vez de las 4.452 del gerente (1,4 MB)
const POR_PAGINA = 50

// INV-28 (V1): las alertas con IA llegan aparte; las de reglas no las esperan
const AVISO_CARGA_IA = 'La primera consulta calcula el pronóstico de toda la red: tarda cerca de 30 s.'

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
  const [recargasIA, setRecargasIA] = useState(0)

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
    setRecargasIA(n => n + 1)
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

      <AlertasIA sucursalId={sucursalId} recargas={recargasIA} />
    </div>
  )
}

// ── Alertas con IA (INV-28) ─────────────────────────
function AlertasIA({ sucursalId, recargas }) {
  const [tipo, setTipo] = useState('')
  const [urgencia, setUrgencia] = useState('')
  const [origen, setOrigen] = useState('')
  const [pagina, setPagina] = useState(1)
  const filtrar = setter => valor => { setter(valor); setPagina(1) }
  // La sucursal también vuelve a la primera página
  const [sucursalAnterior, setSucursalAnterior] = useState(sucursalId)
  if (sucursalAnterior !== sucursalId) {
    setSucursalAnterior(sucursalId)
    setPagina(1)
  }

  const consulta = useConsulta(
    op => getAlertasML({
      tipo: tipo || undefined, urgencia: urgencia || undefined, origen: origen || undefined, sucursalId,
      page: pagina, pageSize: POR_PAGINA,
    }, op),
    [tipo, urgencia, origen, sucursalId, pagina, recargas],
  )

  return (
    <section aria-label="Alertas con IA" className="space-y-3 pt-2 border-t border-slate-200">
      <div>
        <h3 className="text-base font-bold text-slate-800 flex items-center">
          Alertas con IA <DistintivoIA />
        </h3>
        <p className="text-xs text-slate-500">
          Calculadas con la demanda prevista para los próximos 15 días hábiles
          {consulta.datos && <> · {fmtConteo(consulta.datos.total, 'alerta', 'alertas')} · {fmtFecha(consulta.datos.fecha_inventario)}</>}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Filtro etiqueta="Tipo de alerta con IA" vacio="Todos los tipos" opciones={TIPOS_ALERTA_ML}
          valor={tipo} onChange={filtrar(setTipo)} />
        <Filtro etiqueta="Urgencia de alerta con IA" vacio="Todas las urgencias" opciones={URGENCIAS}
          valor={urgencia} onChange={filtrar(setUrgencia)} />
        <Filtro etiqueta="Origen" vacio="Todos los orígenes" opciones={ORIGENES_ALERTA_ML}
          valor={origen} onChange={filtrar(setOrigen)} />
      </div>

      <EstadoConsulta consulta={consulta} aviso={AVISO_CARGA_IA}>
        {d => d.items.length ? (
          <div className="space-y-2">
            {d.items.map(a => <TarjetaAlerta key={`${a.tipo}-${a.codigo_item}-${a.id_sucursal}`} alerta={a} ia />)}
            <Paginacion actual={d.page} paginas={d.pages} total={d.total} setPagina={setPagina} de=" de alertas con IA" />
          </div>
        ) : (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-6 text-center">
            <p className="text-slate-700 font-semibold">Sin alertas con IA</p>
            <p className="text-slate-500 text-sm mt-1">
              No hay alertas con IA que coincidan con los filtros. La Bodega Central no genera alertas con IA porque no vende.
            </p>
          </div>
        )}
      </EstadoConsulta>
    </section>
  )
}

function Filtro({ etiqueta, vacio, opciones, valor, onChange }) {
  return (
    <select aria-label={etiqueta} value={valor} onChange={e => onChange(e.target.value)}
      className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden">
      <option value="">{vacio}</option>
      {Object.entries(opciones).map(([v, texto]) => <option key={v} value={v}>{texto}</option>)}
    </select>
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
      {items.map(alerta => (
        <TarjetaAlerta key={`${alerta.tipo}-${alerta.id_producto}-${alerta.id_sucursal}`} alerta={alerta} />
      ))}
      <Paginacion actual={actual} paginas={paginas} total={total} setPagina={setPagina} />
    </div>
  )
}

// Una alerta de reglas o con IA (ia: distintivo y origen, INV-28 V9)
function TarjetaAlerta({ alerta, ia = false }) {
  const style = URGENCIA_STYLE[alerta.urgencia] || URGENCIA_STYLE.media
  const Icon = style.icon
  return (
    <div className={`${style.bg} border-l-4 ${style.border} rounded-r-lg p-3 flex items-start gap-3 shadow-xs`}>
      <div className={`p-1.5 rounded-md ${style.iconColor}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-bold text-slate-800">
              {alerta.nombre_producto ?? alerta.codigo_item}{ia && <DistintivoIA />}
            </p>
            <p className="text-xs text-slate-500">
              {alerta.sucursal}{alerta.tipo_ubicacion === BODEGA && <DistintivoBodega />} · {etiquetaTipoAlerta(alerta.tipo)}
              {ia && alerta.origen === 'ambos' && <> · {ORIGENES_ALERTA_ML.ambos}</>}
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
}

function Paginacion({ actual, paginas, total, setPagina, de = '' }) {
  if (!(paginas > 1)) return null
  return (
    <div className="flex items-center justify-between pt-2">
      <p className="text-xs text-slate-500">
        Página {actual} de {paginas} · {fmtNumero(total)} alertas
      </p>
      <div className="flex gap-1">
        <button aria-label={`Página anterior${de}`} onClick={() => setPagina(Math.max(1, actual - 1))} disabled={actual === 1}
          className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button aria-label={`Página siguiente${de}`} onClick={() => setPagina(Math.min(paginas, actual + 1))}
          disabled={actual >= paginas}
          className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
