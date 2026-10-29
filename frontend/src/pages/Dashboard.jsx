import { getKPIs, getInventarioResumen, getAlertasResumen, getVentasTendencia, getTopProductos } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import { DollarSign, Calendar, AlertTriangle, Layers, TrendingUp, TrendingDown, Info } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { fmtFecha, fmtMonedaCorta as fmt, fmtNumero } from '../utils/formato'
import { etiquetaTipoAlerta } from '../utils/etiquetas'

const TARJETA = 'bg-white p-4 rounded-xl shadow-xs border border-slate-100'

function KPICard({ icon: Icon, label, detalle, value, variation, color = 'blue' }) {
  const bgMap = { blue: 'bg-blue-50 text-brand-blue', amber: 'bg-amber-50 text-amber-600', slate: 'bg-slate-50 text-slate-500' }
  return (
    <div className={TARJETA}>
      <div className="flex justify-between items-start mb-2">
        <div className={`p-1.5 rounded-lg ${bgMap[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        {variation !== null && variation !== undefined && (
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5
            ${variation >= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
            {variation >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {Math.abs(variation)}%
          </span>
        )}
      </div>
      <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">{label}</p>
      {detalle && <p className="text-slate-400 text-[11px]">{detalle}</p>}
      <p className="text-xl font-bold text-slate-800">{value}</p>
    </div>
  )
}

// Las ventas se rotulan con la fecha de la foto, no con "hoy" (A3.2); la
// Bodega no vende y solo muestra lo que sí tiene datos (H1)
function KPIs({ kpis, esBodega }) {
  const fecha = fmtFecha(kpis.fecha_referencia)
  const mes = fecha.split(' ').slice(1).join(' ')
  return (
    <div className={`grid gap-3 ${esBodega ? 'grid-cols-2' : 'grid-cols-2 lg:grid-cols-4'}`}>
      {!esBodega && (
        <>
          <KPICard icon={DollarSign} label="Ventas del día" detalle={fecha} value={fmt(kpis.ventas_hoy || 0)}
            variation={kpis.variacion_ventas_hoy_pct} />
          <KPICard icon={Calendar} label="Ventas del mes" detalle={mes} value={fmt(kpis.ventas_mes || 0)}
            variation={kpis.variacion_ventas_mes_pct} />
        </>
      )}
      <KPICard icon={AlertTriangle} label="En riesgo" value={fmtNumero(kpis.productos_en_riesgo || 0)} color="amber" />
      <KPICard icon={Layers} label="Stock valorizado" value={fmt(kpis.stock_valorizado || 0)} color="slate" />
    </div>
  )
}

// Los cuatro estados de la API; inconsistencia es el stock negativo (K3)
const TRAMOS_SEMAFORO = [
  { clave: 'ok', etiqueta: 'OK', barra: 'bg-green-500', texto: 'text-green-800' },
  { clave: 'bajo', etiqueta: 'Bajo', barra: 'bg-amber-500', texto: 'text-amber-800' },
  { clave: 'critico', etiqueta: 'Crítico', barra: 'bg-red-500', texto: 'text-red-800' },
  { clave: 'inconsistencia', etiqueta: 'Inconsistencia', barra: 'bg-violet-500', texto: 'text-violet-800' },
]

function SemaforoBar({ data }) {
  const pct = n => (data.total > 0 ? (n / data.total) * 100 : 0)

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">Semáforo de inventario</h3>
      <div className="w-full h-3 rounded-full overflow-hidden flex mb-2">
        {TRAMOS_SEMAFORO.map(t => (
          <div key={t.clave} className={`h-full ${t.barra} transition-all`} style={{ width: `${pct(data[t.clave])}%` }} />
        ))}
      </div>
      <div className="flex justify-between gap-2 text-xs">
        {TRAMOS_SEMAFORO.map(t => (
          <span key={t.clave} className={`${t.texto} font-semibold`}>{fmtNumero(data[t.clave])} {t.etiqueta}</span>
        ))}
      </div>
    </div>
  )
}

function AlertasWidget({ data }) {
  const { global_, por_tipo } = data

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">Alertas activas</h3>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center p-2 bg-red-50 rounded-lg border border-red-100">
          <p className="text-lg font-bold text-red-900">{fmtNumero(global_.critica)}</p>
          <p className="text-xs font-semibold text-red-600">Críticas</p>
        </div>
        <div className="text-center p-2 bg-amber-50 rounded-lg border border-amber-100">
          <p className="text-lg font-bold text-amber-900">{fmtNumero(global_.alta)}</p>
          <p className="text-xs font-semibold text-amber-600">Altas</p>
        </div>
        <div className="text-center p-2 bg-blue-50 rounded-lg border border-blue-100">
          <p className="text-lg font-bold text-blue-900">{fmtNumero(global_.media)}</p>
          <p className="text-xs font-semibold text-blue-600">Medias</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {Object.entries(por_tipo).map(([tipo, count]) => (
          <div key={tipo} className="flex justify-between items-center text-xs">
            <span className="text-slate-600">{etiquetaTipoAlerta(tipo)}</span>
            <span className="font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded-full">{fmtNumero(count)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SinDatos({ titulo, texto }) {
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-2">{titulo}</h3>
      <p className="text-xs text-slate-500">{texto}</p>
    </div>
  )
}

function TendenciaChart({ data }) {
  const titulo = 'Tendencia de ventas (30 días)'
  if (!data.series?.[0]?.puntos?.length) return <SinDatos titulo={titulo} texto="Sin ventas en el período." />
  const puntos = data.series[0].puntos.map(p => ({
    fecha: p.fecha.slice(5),
    valor: Math.round(p.valor_total),
    ma7: p.promedio_movil_7d ? Math.round(p.promedio_movil_7d) : null,
  }))

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3 flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-brand-blue" />
        {titulo}
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={puntos}>
          <defs>
            <linearGradient id="colorVal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="fecha" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => fmt(v)} width={55} />
          <Tooltip formatter={(v) => [`${fmt(v)} COP`, '']} labelStyle={{ fontSize: 11 }} />
          <Area type="monotone" dataKey="valor" stroke="#3B82F6" strokeWidth={2} fill="url(#colorVal)" />
          <Area type="monotone" dataKey="ma7" stroke="#14B8A6" strokeWidth={1.5} strokeDasharray="4 2" fill="none" />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 justify-center">
        <span className="flex items-center gap-1 text-xs text-slate-500">
          <span className="w-3 h-0.5 bg-brand-blue inline-block rounded-sm" /> Ventas
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-500">
          <span className="w-3 h-0.5 bg-brand-teal inline-block rounded-sm border-dashed" /> MA 7d
        </span>
      </div>
    </div>
  )
}

function TopProductosChart({ data }) {
  const titulo = 'Top 5 productos'
  if (!data.items?.length) return <SinDatos titulo={titulo} texto="Sin ventas en el período." />
  const items = data.items.slice(0, 5).map(p => ({
    nombre: p.nombre.length > 25 ? p.nombre.slice(0, 25) + '...' : p.nombre,
    valor: Math.round(p.valor_total),
  }))

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">{titulo}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={items} layout="vertical" margin={{ left: 0 }}>
          <XAxis type="number" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => fmt(v)} />
          <YAxis type="category" dataKey="nombre" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} width={120} />
          <Tooltip formatter={(v) => [`${fmt(v)} COP`, 'Ventas']} />
          <Bar dataKey="valor" fill="#2563EB" radius={[0, 4, 4, 0]} barSize={16} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Dashboard() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector, esBodega } = useSucursal()

  // Cada bloque carga y falla por separado (A3.2); con la Bodega no se piden ventas (H1)
  const kpis = useConsulta(op => getKPIs(sucursalId, op), [sucursalId])
  const semaforo = useConsulta(op => getInventarioResumen(sucursalId, op), [sucursalId])
  const alertas = useConsulta(op => getAlertasResumen(sucursalId, op), [sucursalId])
  const tendencia = useConsulta(op => getVentasTendencia({ dias: 30, sucursalId }, op), [sucursalId], { activo: !esBodega })
  const top = useConsulta(op => getTopProductos(5, sucursalId, op), [sucursalId], { activo: !esBodega })

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800">Dashboard</h2>
        {showSelector && (
          <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />
        )}
      </div>

      <EstadoConsulta consulta={kpis} alto="h-24">
        {k => <KPIs kpis={k} esBodega={esBodega} />}
      </EstadoConsulta>

      {esBodega && (
        <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-100 rounded-xl text-xs text-blue-800">
          <Info className="w-4 h-4 shrink-0" />
          La Bodega Central no vende: las ventas se ven por sucursal.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {!esBodega && (
          <div className="lg:col-span-2">
            <EstadoConsulta consulta={tendencia}>{d => <TendenciaChart data={d} />}</EstadoConsulta>
          </div>
        )}
        <EstadoConsulta consulta={semaforo}>{d => <SemaforoBar data={d.global_} />}</EstadoConsulta>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {!esBodega && (
          <EstadoConsulta consulta={top}>{d => <TopProductosChart data={d} />}</EstadoConsulta>
        )}
        <EstadoConsulta consulta={alertas}>{d => <AlertasWidget data={d} />}</EstadoConsulta>
      </div>

      {kpis.datos?.fecha_referencia && (
        <p className="text-xs text-slate-400 text-center">
          Datos al {fmtFecha(kpis.datos.fecha_referencia)}
        </p>
      )}
    </div>
  )
}
