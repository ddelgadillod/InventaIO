import { useState, useEffect } from 'react'
import { getKPIs, getInventarioResumen, getAlertasResumen, getVentasTendencia, getTopProductos } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import SucursalSelector from '../components/SucursalSelector'
import { DollarSign, Calendar, AlertTriangle, Layers, TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'

function fmt(n) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

function KPICard({ icon: Icon, label, value, variation, color = 'blue' }) {
  const bgMap = { blue: 'bg-blue-50 text-brand-blue', amber: 'bg-amber-50 text-amber-600', slate: 'bg-slate-50 text-slate-500' }
  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100">
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
      <p className="text-xl font-bold text-slate-800">{value}</p>
    </div>
  )
}

function SemaforoBar({ data }) {
  if (!data) return null
  const { ok, bajo, critico, total } = data
  const pOk = total > 0 ? (ok / total * 100) : 0
  const pBajo = total > 0 ? (bajo / total * 100) : 0
  const pCrit = total > 0 ? (critico / total * 100) : 0

  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100">
      <h3 className="font-bold text-slate-800 text-sm mb-3">Semáforo de inventario</h3>
      <div className="w-full h-3 rounded-full overflow-hidden flex mb-2">
        <div className="h-full bg-green-500 transition-all" style={{ width: `${pOk}%` }} />
        <div className="h-full bg-amber-500 transition-all" style={{ width: `${pBajo}%` }} />
        <div className="h-full bg-red-500 transition-all" style={{ width: `${pCrit}%` }} />
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-green-800 font-semibold">{ok} OK</span>
        <span className="text-amber-800 font-semibold">{bajo} Bajo</span>
        <span className="text-red-800 font-semibold">{critico} Crítico</span>
      </div>
    </div>
  )
}

function AlertasWidget({ data }) {
  if (!data) return null
  const { global_, por_tipo } = data

  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100">
      <h3 className="font-bold text-slate-800 text-sm mb-3">Alertas activas</h3>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center p-2 bg-red-50 rounded-lg border border-red-100">
          <p className="text-lg font-bold text-red-900">{global_.critica}</p>
          <p className="text-xs font-semibold text-red-600">Críticas</p>
        </div>
        <div className="text-center p-2 bg-amber-50 rounded-lg border border-amber-100">
          <p className="text-lg font-bold text-amber-900">{global_.alta}</p>
          <p className="text-xs font-semibold text-amber-600">Altas</p>
        </div>
        <div className="text-center p-2 bg-blue-50 rounded-lg border border-blue-100">
          <p className="text-lg font-bold text-blue-900">{global_.media}</p>
          <p className="text-xs font-semibold text-blue-600">Medias</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {Object.entries(por_tipo).map(([tipo, count]) => (
          <div key={tipo} className="flex justify-between items-center text-xs">
            <span className="text-slate-600">{tipo.replace(/_/g, ' ')}</span>
            <span className="font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded-full">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TendenciaChart({ data }) {
  if (!data || !data.series?.[0]?.puntos?.length) return null
  const puntos = data.series[0].puntos.map(p => ({
    fecha: p.fecha.slice(5),
    valor: Math.round(p.valor_total),
    ma7: p.promedio_movil_7d ? Math.round(p.promedio_movil_7d) : null,
  }))

  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100">
      <h3 className="font-bold text-slate-800 text-sm mb-3 flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-brand-blue" />
        Tendencia de ventas (30 días)
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
          <span className="w-3 h-0.5 bg-brand-blue inline-block rounded" /> Ventas
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-500">
          <span className="w-3 h-0.5 bg-brand-teal inline-block rounded border-dashed" /> MA 7d
        </span>
      </div>
    </div>
  )
}

function TopProductosChart({ data }) {
  if (!data?.items?.length) return null
  const items = data.items.slice(0, 5).map(p => ({
    nombre: p.nombre.length > 25 ? p.nombre.slice(0, 25) + '...' : p.nombre,
    valor: Math.round(p.valor_total),
  }))

  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100">
      <h3 className="font-bold text-slate-800 text-sm mb-3">Top 5 productos</h3>
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
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()

  const [kpis, setKpis] = useState(null)
  const [semaforo, setSemaforo] = useState(null)
  const [alertas, setAlertas] = useState(null)
  const [tendencia, setTendencia] = useState(null)
  const [topProd, setTopProd] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      getKPIs(sucursalId).then(setKpis),
      getInventarioResumen(sucursalId).then(setSemaforo),
      getAlertasResumen(sucursalId).then(setAlertas),
      getVentasTendencia(30, sucursalId).then(setTendencia),
      getTopProductos(5, sucursalId).then(setTopProd),
    ])
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [sucursalId]) // recarga cada vez que cambia la sucursal

  if (error) {
    return (
      <div className="p-6">
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          Error cargando datos: {error}
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header con selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800">Dashboard</h2>
        {showSelector && (
          <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-brand-blue" />
        </div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KPICard icon={DollarSign} label="Ventas hoy" value={fmt(kpis?.ventas_hoy || 0)}
              variation={kpis?.variacion_ventas_hoy_pct} color="blue" />
            <KPICard icon={Calendar} label="Ventas mes" value={fmt(kpis?.ventas_mes || 0)}
              variation={kpis?.variacion_ventas_mes_pct} color="blue" />
            <KPICard icon={AlertTriangle} label="En riesgo" value={kpis?.productos_en_riesgo || 0}
              variation={null} color="amber" />
            <KPICard icon={Layers} label="Stock valorizado" value={fmt(kpis?.stock_valorizado || 0)}
              variation={null} color="slate" />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <TendenciaChart data={tendencia} />
            </div>
            <SemaforoBar data={semaforo?.global_} />
          </div>

          {/* Bottom row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TopProductosChart data={topProd} />
            <AlertasWidget data={alertas} />
          </div>

          {kpis?.fecha_referencia && (
            <p className="text-xs text-slate-400 text-center">
              Datos al {kpis.fecha_referencia}
            </p>
          )}
        </>
      )}
    </div>
  )
}
