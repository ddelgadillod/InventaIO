import { useMemo, useState } from 'react'
import { getAlertas, getAlertasML, getAlertasResumen, getCategorias } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DistintivoBodega from '../components/DistintivoBodega'
import DistintivoIA from '../components/DistintivoIA'
import FiltroMultiple from '../components/FiltroMultiple'
import { AlertTriangle, XCircle, Clock, RotateCcw, ChevronLeft, ChevronRight, Sparkles } from 'lucide-react'
import { fmtConteo, fmtFecha, fmtNumero } from '../utils/formato'
import {
  ACCIONES_ALERTA_ML, BODEGA, ORIGENES_ALERTA_ML, TIPOS_ALERTA, TIPOS_ALERTA_ML, URGENCIAS, etiquetaTipoAlerta,
} from '../utils/etiquetas'

// La API pagina (K2): se piden de a 50 en vez de las 4.452 del gerente (1,4 MB)
const POR_PAGINA = 50

// INV-28 (V1): las alertas con IA tienen su propia consulta; las de reglas no las esperan
const AVISO_CARGA_IA = 'La primera consulta calcula el pronóstico de toda la red: tarda cerca de 30 s.'

const URGENCIA_STYLE = {
  critica: { bg: 'bg-red-50',    border: 'border-l-red-600',    icon: XCircle,       iconColor: 'text-red-600',    badge: 'bg-red-100 text-red-700' },
  alta:    { bg: 'bg-amber-50',  border: 'border-l-amber-500',  icon: AlertTriangle, iconColor: 'text-amber-600',  badge: 'bg-amber-100 text-amber-700' },
  media:   { bg: 'bg-blue-50',   border: 'border-l-blue-400',   icon: Clock,         iconColor: 'text-blue-500',   badge: 'bg-blue-100 text-blue-700' },
}

export default function Alertas() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()
  // INV-28 (V12): se elige primero qué alertas ver; solo se consulta la pestaña abierta
  const [vista, setVista] = useState('reglas')

  // V13: cada filtro admite varios valores; una lista vacía es "todos"
  const [filtroTipo, setFiltroTipo] = useState([])
  const [filtroUrgencia, setFiltroUrgencia] = useState([])
  const [pagina, setPagina] = useState(1)
  const [recargasIA, setRecargasIA] = useState(0)

  // Cambiar un filtro vuelve a la primera página
  const filtrar = setter => valor => { setter(valor); setPagina(1) }
  const enReglas = vista === 'reglas'

  const lista = useConsulta(
    op => getAlertas({ tipo: filtroTipo, urgencia: filtroUrgencia, sucursalId, page: pagina, pageSize: POR_PAGINA }, op),
    [filtroTipo, filtroUrgencia, sucursalId, pagina],
    { activo: enReglas },
  )
  const resumen = useConsulta(op => getAlertasResumen(sucursalId, op), [sucursalId], { activo: enReglas })

  const actualizar = () => {
    if (enReglas) {
      lista.recargar()
      resumen.recargar()
    } else setRecargasIA(n => n + 1)
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Alertas</h2>
          <p className="text-xs text-slate-500">
            {enReglas ? 'Por reglas de inventario: cobertura y ventas registradas' : 'Con IA: según el pronóstico de demanda de los próximos 15 días hábiles'}
          </p>
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

      <div role="tablist" aria-label="Tipo de alertas" className="flex gap-1 border-b border-slate-200">
        {Object.entries(VISTAS).map(([clave, etiqueta]) => (
          <button key={clave} role="tab" aria-selected={vista === clave} onClick={() => setVista(clave)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-semibold -mb-px border-b-2 ${vista === clave
              ? 'border-brand-blue text-brand-blue' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {clave === 'ia' && <Sparkles className="w-4 h-4" aria-hidden="true" />}{etiqueta}
          </button>
        ))}
      </div>

      {enReglas && (
        <div role="tabpanel" aria-label="Alertas por reglas" className="space-y-5">
          {lista.datos && (
            <p className="text-xs text-slate-500">
              {fmtConteo(lista.datos.total, 'alerta activa', 'alertas activas')} · {fmtFecha(lista.datos.fecha_inventario)}
            </p>
          )}

          <EstadoConsulta consulta={resumen} alto="h-20">
            {r => <Resumen global_={r.global_} />}
          </EstadoConsulta>

          <div className="flex flex-wrap gap-2">
            <FiltroMultiple etiqueta="Tipo" vacio="Todos los tipos" plural="tipos" opciones={TIPOS_ALERTA}
              valores={filtroTipo} onChange={filtrar(setFiltroTipo)} />
            <FiltroMultiple etiqueta="Urgencia" vacio="Todas las urgencias" plural="urgencias" opciones={URGENCIAS}
              valores={filtroUrgencia} onChange={filtrar(setFiltroUrgencia)} />
          </div>

          <EstadoConsulta consulta={lista}>
            {d => <Lista datos={d} setPagina={setPagina} />}
          </EstadoConsulta>
        </div>
      )}

      {/* Montada siempre para conservar sus filtros al cambiar de pestaña; consulta solo si está abierta */}
      <AlertasIA activo={!enReglas} sucursalId={sucursalId} recargas={recargasIA} />
    </div>
  )
}

const VISTAS = { reglas: 'Por reglas', ia: 'Con IA' }

// ── Alertas con IA (INV-28) ─────────────────────────
function AlertasIA({ activo, sucursalId, recargas }) {
  const [tipo, setTipo] = useState([])
  const [urgencia, setUrgencia] = useState([])
  const [origen, setOrigen] = useState([])
  const [categoria, setCategoria] = useState([])
  const [pagina, setPagina] = useState(1)
  const filtrar = setter => valor => { setter(valor); setPagina(1) }
  // La sucursal también vuelve a la primera página
  const [sucursalAnterior, setSucursalAnterior] = useState(sucursalId)
  if (sucursalAnterior !== sucursalId) {
    setSucursalAnterior(sucursalId)
    setPagina(1)
  }

  const consulta = useConsulta(
    op => getAlertasML({ tipo, urgencia, origen, categoria, sucursalId, page: pagina, pageSize: POR_PAGINA }, op),
    [tipo, urgencia, origen, categoria, sucursalId, pagina, recargas],
    { activo },
  )
  // V14: categorías de la bodega, como en Recomendaciones (una sola carga al abrir la pestaña)
  const categorias = useConsulta(op => getCategorias(op), [], { activo })
  const opcionesCategoria = useMemo(() => Object.fromEntries(
    (categorias.datos?.items ?? []).map(c => c.categoria).sort((a, b) => a.localeCompare(b, 'es')).map(c => [c, c]),
  ), [categorias.datos])
  // Las tarjetas, como las de reglas, solo cambian con la sucursal; comparte la caché del Core API
  const resumen = useConsulta(op => getAlertasML({ sucursalId, page: 1, pageSize: 1 }, op), [sucursalId, recargas],
    { activo })

  if (!activo) return null
  // Un solo mensaje de error: el de la lista, y su "Reintentar" repite también el resumen
  const lista = { ...consulta, recargar: () => { consulta.recargar(); resumen.recargar() } }
  return (
    <div role="tabpanel" aria-label="Alertas con IA" className="space-y-5">
      {consulta.datos && (
        <p className="text-xs text-slate-500">
          {fmtConteo(consulta.datos.total, 'alerta', 'alertas')} · foto del {fmtFecha(consulta.datos.fecha_inventario)}
          {consulta.datos.fecha_pronostico && <> · pronóstico con datos al {fmtFecha(consulta.datos.fecha_pronostico)}</>}
        </p>
      )}

      {!resumen.error && (
        <EstadoConsulta consulta={resumen} alto="h-20">
          {r => <ResumenIA resumen={r.resumen} />}
        </EstadoConsulta>
      )}

      <div className="flex flex-wrap gap-2">
        <FiltroMultiple etiqueta="Tipo de alerta con IA" vacio="Todos los tipos" plural="tipos"
          opciones={TIPOS_ALERTA_ML} valores={tipo} onChange={filtrar(setTipo)} />
        <FiltroMultiple etiqueta="Urgencia de alerta con IA" vacio="Todas las urgencias" plural="urgencias"
          opciones={URGENCIAS} valores={urgencia} onChange={filtrar(setUrgencia)} />
        <FiltroMultiple etiqueta="Origen" vacio="Todos los orígenes" plural="orígenes"
          opciones={ORIGENES_ALERTA_ML} valores={origen} onChange={filtrar(setOrigen)} />
        <FiltroMultiple etiqueta="Categoría" vacio="Todas las categorías" plural="categorías"
          opciones={opcionesCategoria} valores={categoria} onChange={filtrar(setCategoria)} />
      </div>

      <EstadoConsulta consulta={lista} aviso={AVISO_CARGA_IA}>
        {d => d.items.length ? (
          <div className="space-y-2">
            {d.items.map(a => <TarjetaAlerta key={`${a.tipo}-${a.codigo_item}-${a.id_sucursal}`} alerta={a} ia />)}
            <Paginacion actual={d.page} paginas={d.pages} total={d.total} setPagina={setPagina} />
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
    </div>
  )
}

function ResumenIA({ resumen }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="bg-white p-3 rounded-xl shadow-xs border border-slate-100 text-center">
        <p className="text-2xl font-bold text-slate-800">{fmtNumero(resumen.total)}</p>
        <p className="text-xs text-slate-500 font-medium">Total</p>
      </div>
      <div className="bg-red-50 p-3 rounded-xl border border-red-100 text-center">
        <p className="text-2xl font-bold text-red-900">{fmtNumero(resumen.riesgo_desabastecimiento_ml)}</p>
        <p className="text-xs text-red-600 font-semibold">Riesgo de desabastecimiento</p>
      </div>
      <div className="bg-blue-50 p-3 rounded-xl border border-blue-100 text-center">
        <p className="text-2xl font-bold text-blue-900">{fmtNumero(resumen.sobrestock_previsto_ml)}</p>
        <p className="text-xs text-blue-600 font-semibold">Sobrestock previsto</p>
      </div>
      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-center">
        <p className="text-2xl font-bold text-slate-800">{fmtNumero(resumen.ambos)}</p>
        <p className="text-xs text-slate-600 font-semibold">También por reglas</p>
      </div>
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
              {ia && alerta.accion && <> · Acción: {ACCIONES_ALERTA_ML[alerta.accion] ?? alerta.accion}</>}
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

function Paginacion({ actual, paginas, total, setPagina }) {
  if (!(paginas > 1)) return null
  return (
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
  )
}
