import { useState, useEffect } from 'react'
import { getInventario } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import SucursalSelector from '../components/SucursalSelector'
import { Loader2, ChevronLeft, ChevronRight, Search } from 'lucide-react'

const SEMAFORO = {
  ok:      { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200', label: '✓ OK' },
  bajo:    { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', label: '⚠ Bajo' },
  critico: { bg: 'bg-red-50',   text: 'text-red-700',   border: 'border-red-200',   label: '✕ Crítico' },
}

export default function Inventario() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [semaforo, setSemaforo] = useState('')
  const [categoria, setCategoria] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [searchInput, setSearchInput] = useState('')

  const load = () => {
    setLoading(true)
    const params = { page, page_size: 15 }
    if (semaforo)    params.semaforo   = semaforo
    if (categoria)   params.categoria  = categoria
    if (busqueda)    params.busqueda   = busqueda
    if (sucursalId)  params.sucursal_id = sucursalId
    getInventario(params)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  // Resetear página al cambiar filtros o sucursal
  useEffect(() => { setPage(1) }, [sucursalId, semaforo, categoria, busqueda])
  useEffect(() => { load() }, [page, sucursalId, semaforo, categoria, busqueda])

  const handleSearch = (e) => {
    e.preventDefault()
    setBusqueda(searchInput)
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Inventario</h2>
          {data && <p className="text-xs text-slate-500">{data.total} productos · {data.fecha_inventario}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Selector de sucursal */}
          {showSelector && (
            <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />
          )}

          {/* Filtro semáforo */}
          <select value={semaforo} onChange={e => setSemaforo(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-none">
            <option value="">Todos los estados</option>
            <option value="ok">✓ OK</option>
            <option value="bajo">⚠ Bajo</option>
            <option value="critico">✕ Crítico</option>
          </select>

          {/* Filtro categoría */}
          <select value={categoria} onChange={e => setCategoria(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-none">
            <option value="">Todas las categorías</option>
            {['Abarrotes','Bebidas','Lácteos','Cárnicos','Panadería','Congelados',
              'Frutas y verduras','Avícola','Mariscos','Huevos','Cuidado personal',
              'Aseo hogar','Hogar','Delicatessen','Bebé'].map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          {/* Búsqueda */}
          <form onSubmit={handleSearch} className="flex">
            <input value={searchInput} onChange={e => setSearchInput(e.target.value)}
              placeholder="Buscar producto..."
              className="h-9 w-40 px-3 text-xs rounded-l-lg border border-r-0 border-slate-200 outline-none" />
            <button type="submit" className="h-9 px-2 bg-brand-blue text-white rounded-r-lg">
              <Search className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-brand-blue" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="text-xs text-slate-500 font-semibold uppercase border-b border-slate-100">
                  <th className="px-4 py-3 text-left">Producto</th>
                  <th className="px-4 py-3 text-left">Categoría</th>
                  <th className="px-4 py-3 text-left">Sucursal</th>
                  <th className="px-4 py-3 text-right">Stock</th>
                  <th className="px-4 py-3 text-right">Reorden</th>
                  <th className="px-4 py-3 text-right">Cobertura</th>
                  <th className="px-4 py-3 text-center">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data?.items?.map((item, i) => {
                  const s = SEMAFORO[item.semaforo] || SEMAFORO.ok
                  return (
                    <tr key={i} className={`${item.semaforo === 'critico' ? 'bg-red-50/30' : item.semaforo === 'bajo' ? 'bg-amber-50/20' : ''} hover:bg-slate-50`}>
                      <td className="px-4 py-2.5 font-medium text-slate-800 text-xs">{item.nombre_producto}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-600">{item.categoria}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-600">{item.sucursal}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-xs">{Math.round(item.stock_disponible)}</td>
                      <td className="px-4 py-2.5 text-right text-xs text-slate-500">{Math.round(item.punto_reorden)}</td>
                      <td className="px-4 py-2.5 text-right text-xs font-medium">{item.dias_cobertura.toFixed(1)}d</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`inline-block px-2 py-0.5 text-xs font-bold rounded-full ${s.bg} ${s.text} border ${s.border}`}>
                          {s.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Página {data.page} de {data.pages} · {data.total} total
            </p>
            <div className="flex gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button onClick={() => setPage(p => Math.min(data.pages, p + 1))} disabled={page >= data.pages}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
