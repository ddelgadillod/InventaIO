import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { getInventarioDetalle, getProducto } from '../api/client'
import { useConsulta } from '../hooks/useConsulta'
import DistintivoBodega from './DistintivoBodega'
import EstadoConsulta from './EstadoConsulta'
import { fmtCantidad, fmtFecha } from '../utils/formato'
import { BODEGA, ESTADOS_INVENTARIO, textoCobertura, textoUnidadVenta } from '../utils/etiquetas'

/**
 * Detalle de una fila de Inventario (INV-26 fix, A3.6): inventario/detalle y
 * productos/{id} con su proveedor (J2, J3). La API aplica la regla de
 * permisos de INV-25; un 403 o 404 se muestra dentro del panel.
 */
export default function DetalleInventario({ idProducto, idSucursal, onCerrar }) {
  const detalle = useConsulta(op => getInventarioDetalle(idProducto, idSucursal, op), [idProducto, idSucursal])
  const producto = useConsulta(op => getProducto(idProducto, op), [idProducto])

  useEffect(() => {
    const alTeclear = e => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [onCerrar])

  // En un portal: dentro de la página heredaría márgenes (space-y) y el fondo
  // oscuro no cubriría toda la pantalla
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onCerrar}>
      <aside
        role="dialog"
        aria-label="Detalle de inventario"
        className="w-full max-w-md h-full bg-white shadow-xl p-5 overflow-y-auto space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-slate-800">Detalle de inventario</h3>
          <button onClick={onCerrar} aria-label="Cerrar detalle" className="p-1 rounded-lg hover:bg-slate-100 text-slate-500">
            <X className="w-5 h-5" />
          </button>
        </div>
        <EstadoConsulta consulta={detalle}>
          {d => <Contenido detalle={d} producto={producto} />}
        </EstadoConsulta>
      </aside>
    </div>,
    document.body,
  )
}

// La unidad del stock sale de `unidad` del producto y se dice en la
// descripción; los productos por kilo llevan un decimal
function Contenido({ detalle: d, producto }) {
  const unidad = producto.datos?.unidad
  const cantidad = n => fmtCantidad(n, unidad)
  const estado = d.semaforo
  const filas = [
    ['Stock actual', cantidad(d.stock_actual)],
    ['Stock en la Bodega', d.tipo_ubicacion === BODEGA ? '—' : cantidad(d.stock_bodega)],
    ['Stock mínimo', cantidad(d.stock_minimo)],
    ['Stock máximo', cantidad(d.stock_maximo)],
    ['Punto de reorden', cantidad(d.punto_reorden)],
    ['Cobertura', textoCobertura(d.dias_cobertura, d.stock_actual)],
  ]

  return (
    <div className="space-y-4">
      <div>
        <p className="font-semibold text-slate-800">{d.nombre_producto}</p>
        <p className="text-xs text-slate-500">
          {d.categoria} · {d.sucursal}
          {d.tipo_ubicacion === BODEGA && <DistintivoBodega />}
        </p>
        {producto.datos && (
          <p className="text-xs text-slate-500">
            Código {producto.datos.codigo_item} · {textoUnidadVenta(unidad)}
          </p>
        )}
        <p className="text-xs font-bold mt-1">{ESTADOS_INVENTARIO[estado] ?? estado}</p>
      </div>

      <dl className="grid grid-cols-2 gap-3">
        {filas.map(([etiqueta, valor]) => (
          <div key={etiqueta} className="bg-slate-50 rounded-lg p-2">
            <dt className="text-xs text-slate-500">{etiqueta}</dt>
            <dd className="text-sm font-semibold text-slate-800">{valor}</dd>
          </div>
        ))}
      </dl>

      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase">Proveedor</p>
        <p className="text-sm text-slate-700">{textoProveedor(producto)}</p>
      </div>

      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase">Fotos de inventario</p>
        <ul className="text-sm text-slate-700">
          {d.historial.map(h => (
            <li key={h.fecha}>{fmtFecha(h.fecha)}: {cantidad(h.stock_disponible)}</li>
          ))}
        </ul>
        {d.historial.length === 1 && (
          <p className="text-xs text-slate-400">Hay una sola foto de inventario: todavía no hay una serie para graficar.</p>
        )}
      </div>
    </div>
  )
}

function textoProveedor(producto) {
  if (producto.cargando) return 'Cargando…'
  if (producto.error) return 'No disponible'
  const proveedores = producto.datos?.proveedores ?? []
  return proveedores.length ? proveedores.join(', ') : 'Sin proveedor registrado'
}
