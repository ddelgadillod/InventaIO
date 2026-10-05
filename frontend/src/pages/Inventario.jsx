import { useCallback, useMemo, useState } from 'react'
import { getCategorias, getInventario } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DetalleInventario from '../components/DetalleInventario'
import DistintivoBodega from '../components/DistintivoBodega'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { fmtCantidad, fmtFecha, fmtNumero } from '../utils/formato'
import { BODEGA, ESTADOS_INVENTARIO, textoCobertura } from '../utils/etiquetas'

const POR_PAGINA = 15

const ESTILO_ESTADO = {
  ok:             { fila: '',                badge: 'bg-green-50 text-green-700 border-green-200' },
  bajo:           { fila: 'bg-amber-50/20',  badge: 'bg-amber-50 text-amber-700 border-amber-200' },
  critico:        { fila: 'bg-red-50/30',    badge: 'bg-red-50 text-red-700 border-red-200' },
  inconsistencia: { fila: 'bg-violet-50/30', badge: 'bg-violet-50 text-violet-700 border-violet-200' },
}

export default function Inventario() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector } = useSucursal()

  const [page, setPage] = useState(1)
  const [semaforo, setSemaforo] = useState('')
  const [categoria, setCategoria] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [seleccion, setSeleccion] = useState(null)

  // Cambiar un filtro vuelve a la primera página
  const filtrar = setter => valor => { setter(valor); setPage(1) }

  // Las categorías salen de la bodega, no de una lista fija (A3.4)
  const categorias = useConsulta(op => getCategorias(op), [])
  const nombresCategorias = useMemo(
    () => (categorias.datos?.items ?? []).map(c => c.categoria).sort((a, b) => a.localeCompare(b, 'es')),
    [categorias.datos],
  )

  const inventario = useConsulta(
    op => getInventario(
      { page, page_size: POR_PAGINA, semaforo, categoria, busqueda, sucursal_id: sucursalId }, op),
    [page, sucursalId, semaforo, categoria, busqueda],
  )
  const data = inventario.datos

  const handleSearch = (e) => {
    e.preventDefault()
    filtrar(setBusqueda)(searchInput)
  }
  const cerrarDetalle = useCallback(() => setSeleccion(null), [])

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Inventario</h2>
          {data && <p className="text-xs text-slate-500">{fmtNumero(data.total)} productos · {fmtFecha(data.fecha_inventario)}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {showSelector && (
            <SucursalSelector value={rawSucursalId} onChange={filtrar(setSucursalId)} />
          )}

          <select aria-label="Estado" value={semaforo} onChange={e => filtrar(setSemaforo)(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden">
            <option value="">Todos los estados</option>
            <option value="ok">{ESTADOS_INVENTARIO.ok}</option>
            <option value="bajo">{ESTADOS_INVENTARIO.bajo}</option>
            <option value="critico">{ESTADOS_INVENTARIO.critico}</option>
            <option value="inconsistencia">{ESTADOS_INVENTARIO.inconsistencia}</option>
          </select>

          <select aria-label="Categoría" value={categoria} onChange={e => filtrar(setCategoria)(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden">
            <option value="">Todas las categorías</option>
            {nombresCategorias.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <form onSubmit={handleSearch} className="flex">
            <input value={searchInput} onChange={e => setSearchInput(e.target.value)}
              placeholder="Buscar producto..."
              className="h-9 w-40 px-3 text-xs rounded-l-lg border border-r-0 border-slate-200 outline-hidden" />
            <button type="submit" aria-label="Buscar" className="h-9 px-2 bg-brand-blue text-white rounded-r-lg">
              <Search className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-xs border border-slate-100 overflow-hidden">
        <EstadoConsulta consulta={inventario}>
          {d => <Tabla items={d.items} onElegir={setSeleccion} />}
        </EstadoConsulta>

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Página {data.page} de {data.pages} · {fmtNumero(data.total)} total
            </p>
            <div className="flex gap-1">
              <button aria-label="Página anterior" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button aria-label="Página siguiente" onClick={() => setPage(p => Math.min(data.pages, p + 1))}
                disabled={page >= data.pages}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {seleccion && (
        <DetalleInventario idProducto={seleccion.idProducto} idSucursal={seleccion.idSucursal} onCerrar={cerrarDetalle} />
      )}
    </div>
  )
}

function Tabla({ items, onElegir }) {
  if (!items.length) {
    return <p className="p-6 text-center text-sm text-slate-500">No hay productos que coincidan con los filtros.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[820px]">
        <thead>
          <tr className="text-xs text-slate-500 font-semibold uppercase border-b border-slate-100">
            <th className="px-4 py-3 text-left">Producto</th>
            <th className="px-4 py-3 text-left">Categoría</th>
            <th className="px-4 py-3 text-left">Sucursal</th>
            <th className="px-4 py-3 text-right">Stock</th>
            <th className="px-4 py-3 text-right">Stock Bodega</th>
            <th className="px-4 py-3 text-right">Reorden</th>
            <th className="px-4 py-3 text-right">Cobertura</th>
            <th className="px-4 py-3 text-center">Estado</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {items.map(item => {
            const estado = item.semaforo
            const estilo = ESTILO_ESTADO[estado] || ESTILO_ESTADO.ok
            const esBodega = item.tipo_ubicacion === BODEGA
            return (
              <tr key={`${item.id_producto}-${item.id_sucursal}`} className={`${estilo.fila} hover:bg-slate-50`}>
                <td className="px-4 py-2.5 text-xs">
                  <button
                    onClick={() => onElegir({ idProducto: item.id_producto, idSucursal: item.id_sucursal })}
                    className="font-medium text-slate-800 text-left hover:text-brand-blue hover:underline"
                  >
                    {item.nombre_producto}
                  </button>
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-600">{item.categoria}</td>
                <td className="px-4 py-2.5 text-xs text-slate-600">
                  {item.sucursal}{esBodega && <DistintivoBodega />}
                </td>
                <td className="px-4 py-2.5 text-right font-bold text-xs">{fmtCantidad(item.stock_disponible, item.unidad)}</td>
                <td className="px-4 py-2.5 text-right text-xs text-slate-600">
                  {esBodega ? '—' : fmtCantidad(item.stock_bodega, item.unidad)}
                </td>
                <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmtCantidad(item.punto_reorden, item.unidad)}</td>
                <td className="px-4 py-2.5 text-right text-xs font-medium">
                  {textoCobertura(item.dias_cobertura, item.stock_disponible)}
                </td>
                <td className="px-4 py-2.5 text-center">
                  <span className={`inline-block px-2 py-0.5 text-xs font-bold rounded-full border whitespace-nowrap ${estilo.badge}`}>
                    {ESTADOS_INVENTARIO[estado] ?? estado}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
