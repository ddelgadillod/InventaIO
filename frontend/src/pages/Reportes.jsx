import { useMemo, useState } from 'react'
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Info, TrendingDown, TrendingUp } from 'lucide-react'
import {
  getCategorias, getComparativa, getDistribucionCategorias, getValorizado, getVentas, getVentasTendencia,
} from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DistintivoBodega from '../components/DistintivoBodega'
import { fmtConteo, fmtFecha, fmtMonedaCorta as fmt, fmtNumero, fmtPeriodo } from '../utils/formato'
import { esPuntoAislado } from '../utils/graficas'
import { AGRUPACIONES, BODEGA, nombreSerieVentas, nombreUbicacion } from '../utils/etiquetas'
import { AGRUPACION_DEL_ATAJO, ATAJOS, rangoDelAtajo } from '../utils/periodos'

/**
 * Reportes de ventas (INV-26 fix, A9): ventas y comparativa, distribución por
 * categorías, tendencia por sucursal y valorizado del inventario, con los
 * filtros de K7. Con la Bodega elegida solo se ve el valorizado (no vende).
 */
const TARJETA = 'bg-white p-4 rounded-xl shadow-xs border border-slate-100'
const COLORES_SERIE = ['#2563EB', '#14B8A6', '#F59E0B', '#8B5CF6']
const CAMPO_FECHA = 'h-9 px-2 text-xs rounded-lg border border-slate-200 bg-white outline-hidden'

export default function Reportes() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector, esBodega } = useSucursal()
  const [atajo, setAtajo] = useState('mes')
  const [periodo, setPeriodo] = useState(null) // { desde, hasta } elegido; null = el del atajo inicial
  const [agrupacion, setAgrupacion] = useState(AGRUPACION_DEL_ATAJO.mes)
  const [categoria, setCategoria] = useState('')

  // El rango de datos (primera y última venta) sale de la API
  const limites = useConsulta(op => getVentas({}, op), [])
  const rango = limites.datos && { desde: limites.datos.datos_desde, hasta: limites.datos.datos_hasta }
  const actual = periodo ?? (rango && rangoDelAtajo('mes', rango))
  const periodoValido = !!actual && actual.desde <= actual.hasta

  const elegirAtajo = a => {
    setAtajo(a)
    setPeriodo(rangoDelAtajo(a, rango))
    setAgrupacion(AGRUPACION_DEL_ATAJO[a])
  }
  const cambiarFecha = (campo, valor) => {
    setAtajo('rango')
    setPeriodo({ ...actual, [campo]: valor })
  }

  const filtros = actual && {
    fechaInicio: actual.desde, fechaFin: actual.hasta, sucursalId, categoria: categoria || undefined, agrupacion,
  }
  const deps = [actual?.desde, actual?.hasta, sucursalId, categoria, agrupacion]
  const conVentas = periodoValido && !esBodega
  const ventas = useConsulta(op => getVentas(filtros, op), deps, { activo: conVentas })
  const comparativa = useConsulta(op => getComparativa(filtros, op), deps, { activo: conVentas && atajo !== 'todo' })
  const distribucion = useConsulta(op => getDistribucionCategorias(filtros, op), deps, { activo: conVentas })
  const tendencia = useConsulta(op => getVentasTendencia({ ...filtros, porSucursal: true }, op), deps,
    { activo: conVentas })
  const valorizado = useConsulta(op => getValorizado(sucursalId, op), [sucursalId])
  const categorias = useConsulta(op => getCategorias(op), [])

  const nombresCategorias = useMemo(
    () => (categorias.datos?.items ?? []).map(c => c.categoria).sort((a, b) => a.localeCompare(b, 'es')),
    [categorias.datos],
  )

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Reportes de ventas</h2>
          {actual && <p className="text-xs text-slate-500">{fmtFecha(actual.desde)} – {fmtFecha(actual.hasta)}</p>}
        </div>
        {showSelector && <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />}
      </div>

      <EstadoConsulta consulta={limites} alto="h-16">{() => null}</EstadoConsulta>

      {rango && (
        <div className="flex flex-wrap items-center gap-2">
          {Object.entries(ATAJOS).map(([clave, etiqueta]) => (
            <button key={clave} onClick={() => elegirAtajo(clave)} aria-pressed={atajo === clave}
              className={`h-9 px-3 text-xs font-medium rounded-lg border ${atajo === clave
                ? 'bg-brand-blue text-white border-brand-blue' : 'bg-white text-slate-700 border-slate-200'}`}>
              {etiqueta}
            </button>
          ))}
          <label className="text-xs text-slate-500">Desde
            <input type="date" aria-label="Desde" value={actual.desde} min={rango.desde} max={rango.hasta}
              onChange={e => cambiarFecha('desde', e.target.value)} className={`ml-1 ${CAMPO_FECHA}`} />
          </label>
          <label className="text-xs text-slate-500">Hasta
            <input type="date" aria-label="Hasta" value={actual.hasta} min={rango.desde} max={rango.hasta}
              onChange={e => cambiarFecha('hasta', e.target.value)} className={`ml-1 ${CAMPO_FECHA}`} />
          </label>
          <select aria-label="Agrupación" value={agrupacion} onChange={e => setAgrupacion(e.target.value)} className={CAMPO_FECHA}>
            {Object.entries(AGRUPACIONES).map(([valor, etiqueta]) => <option key={valor} value={valor}>{etiqueta}</option>)}
          </select>
          <select aria-label="Categoría" value={categoria} onChange={e => setCategoria(e.target.value)} className={CAMPO_FECHA}>
            <option value="">Todas las categorías</option>
            {nombresCategorias.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      )}

      {actual && !periodoValido && (
        <p role="alert" className="text-sm text-red-600">La fecha inicial es posterior a la final.</p>
      )}

      {esBodega ? (
        <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-100 rounded-xl text-xs text-blue-800">
          <Info className="w-4 h-4 shrink-0" />
          La Bodega Central no vende: las ventas se ven por sucursal. Aquí se ve su inventario valorizado.
        </div>
      ) : periodoValido && (
        <>
          <EstadoConsulta consulta={ventas}>{d => <Ventas datos={d} />}</EstadoConsulta>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {atajo === 'todo'
              ? <Nota titulo="Comparativa" texto="No aplica a toda la historia: no hay un período anterior." />
              : <EstadoConsulta consulta={comparativa}>{d => <Comparativa datos={d} />}</EstadoConsulta>}
            <EstadoConsulta consulta={distribucion}>
              {d => <Distribucion datos={d} categoria={categoria} />}
            </EstadoConsulta>
          </div>
          <EstadoConsulta consulta={tendencia}>{d => <Tendencia datos={d} />}</EstadoConsulta>
        </>
      )}

      <EstadoConsulta consulta={valorizado}>{d => <Valorizado datos={d} categoria={categoria} />}</EstadoConsulta>
    </div>
  )
}

function Nota({ titulo, texto }) {
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-2">{titulo}</h3>
      <p className="text-xs text-slate-500">{texto}</p>
    </div>
  )
}

function Cifra({ etiqueta, valor }) {
  return (
    <div className={TARJETA}>
      <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">{etiqueta}</p>
      <p className="text-xl font-bold text-slate-800">{valor}</p>
    </div>
  )
}

function Ventas({ datos }) {
  if (!datos.items.length) return <Nota titulo="Ventas" texto="Sin ventas en el período." />
  const transacciones = datos.items.reduce((n, i) => n + i.transacciones, 0)
  const barras = datos.items.map(i => ({ periodo: fmtPeriodo(i.periodo), valor: Math.round(i.valor_total) }))
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Cifra etiqueta="Valor vendido" valor={fmt(datos.total_valor)} />
        <Cifra etiqueta="Margen" valor={fmt(datos.total_margen)} />
        <Cifra etiqueta="Cantidad" valor={fmtNumero(datos.total_cantidad)} />
        <Cifra etiqueta="Transacciones" valor={fmtNumero(transacciones)} />
      </div>
      <div className={TARJETA}>
        <h3 className="font-bold text-slate-800 text-sm mb-3">Ventas por {AGRUPACIONES[datos.agrupacion].toLowerCase()}</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={barras}>
            <XAxis dataKey="periodo" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => fmt(v)} width={55} />
            <Tooltip formatter={v => [`${fmt(v)} COP`, 'Ventas']} />
            <Bar dataKey="valor" fill="#2563EB" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function rangoTexto(rango) {
  const [desde, hasta] = rango.split(' / ')
  return `${fmtFecha(desde)} – ${fmtFecha(hasta)}`
}

function Comparativa({ datos }) {
  const r = datos.resumen
  const sube = r.variacion_pct >= 0
  const Icono = sube ? TrendingUp : TrendingDown
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">Comparativa con el período anterior</h3>
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500">Este período</p>
          <p className="text-xl font-bold text-slate-800">{fmt(r.valor_actual)}</p>
          <p className="text-xs text-slate-500 mt-2">{rangoTexto(r.periodo_anterior)}</p>
          <p className="text-sm font-semibold text-slate-600">{fmt(r.valor_anterior)}</p>
        </div>
        <span className={`flex items-center gap-1 text-sm font-bold px-2 py-1 rounded-full
          ${sube ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
          <Icono className="w-4 h-4" />{Math.abs(r.variacion_pct)}%
        </span>
      </div>
    </div>
  )
}

function Distribucion({ datos, categoria }) {
  if (!datos.items.length) return <Nota titulo="Distribución por categorías" texto="Sin ventas en el período." />
  const top = [...datos.items].sort((a, b) => b.participacion_pct - a.participacion_pct).slice(0, 8)
  const resto = datos.items.length - top.length
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">Distribución por categorías</h3>
      <ul className="space-y-1.5">
        {top.map(c => (
          <li key={c.categoria} className={`text-xs ${c.categoria === categoria ? 'font-bold text-brand-blue' : 'text-slate-600'}`}>
            <div className="flex justify-between"><span>{c.categoria}</span><span>{c.participacion_pct.toFixed(1)}%</span></div>
            <div className="h-1.5 bg-slate-100 rounded-full"><div className="h-1.5 bg-brand-blue rounded-full"
              style={{ width: `${c.participacion_pct}%` }} /></div>
          </li>
        ))}
      </ul>
      {resto > 0 && <p className="text-xs text-slate-400 mt-2">Y {fmtConteo(resto, 'categoría', 'categorías')} más.</p>}
    </div>
  )
}

function Tendencia({ datos }) {
  if (!datos.series.length) return <Nota titulo="Tendencia por sucursal" texto="Sin ventas en el período." />
  const nombres = datos.series.map(s => nombreSerieVentas(s.sucursal))
  const filas = {}
  datos.series.forEach((s, i) => s.puntos.forEach(p => {
    filas[p.fecha] = { ...(filas[p.fecha] ?? { periodo: fmtPeriodo(p.fecha) }), [nombres[i]]: Math.round(p.valor_total) }
  }))
  const puntos = Object.keys(filas).sort().map(k => filas[k])
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm mb-3">Tendencia por sucursal</h3>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={puntos}>
          <XAxis dataKey="periodo" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => fmt(v)} width={55} />
          <Tooltip formatter={(v, nombre) => [`${fmt(v)} COP`, nombre]} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {nombres.map((n, i) => {
            const color = COLORES_SERIE[i % COLORES_SERIE.length]
            // Sin puntos, salvo el de un mes aislado, que no traza segmento y no se vería
            const punto = p => (esPuntoAislado(puntos, n, p.index)
              ? <circle key={p.key} cx={p.cx} cy={p.cy} r={3} fill={color} /> : null)
            return <Line key={n} type="monotone" dataKey={n} stroke={color} dot={punto} strokeWidth={2} />
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function Valorizado({ datos, categoria }) {
  const items = categoria ? datos.items.filter(i => i.categoria === categoria) : datos.items
  const total = items.reduce((s, i) => s + i.valor_stock, 0)
  const sumar = clave => Object.values(items.reduce((acc, i) => {
    const k = i[clave]
    acc[k] = { ...i, valor_stock: (acc[k]?.valor_stock ?? 0) + i.valor_stock }
    return acc
  }, {})).sort((a, b) => b.valor_stock - a.valor_stock)
  const ubicaciones = sumar('id_sucursal')
  const porCategoria = sumar('categoria').slice(0, 8)

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm">Inventario valorizado</h3>
      <p className="text-xs text-slate-500 mb-3">
        Foto del {fmtFecha(datos.fecha_inventario)}{categoria && ` · ${categoria}`}: {fmt(total)}
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <table className="text-xs w-full">
          <thead><tr className="text-slate-500 text-left"><th className="py-1">Ubicación</th><th className="py-1 text-right">Valor</th></tr></thead>
          <tbody>
            {ubicaciones.map(u => (
              <tr key={u.id_sucursal} className="border-t border-slate-100">
                <td className="py-1">{nombreUbicacion({ nombre: u.sucursal, tipo: u.tipo_ubicacion })}
                  {u.tipo_ubicacion === BODEGA && <DistintivoBodega />}</td>
                <td className="py-1 text-right font-semibold">{fmt(u.valor_stock)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!categoria && (
          <table className="text-xs w-full">
            <thead><tr className="text-slate-500 text-left"><th className="py-1">Categoría</th><th className="py-1 text-right">Valor</th></tr></thead>
            <tbody>
              {porCategoria.map(c => (
                <tr key={c.categoria} className="border-t border-slate-100">
                  <td className="py-1">{c.categoria}</td>
                  <td className="py-1 text-right font-semibold">{fmt(c.valor_stock)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
