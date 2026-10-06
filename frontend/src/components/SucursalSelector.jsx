import { Building2 } from 'lucide-react'
import { useSucursales } from '../hooks/useSucursales'
import { BODEGA, nombreUbicacion } from '../utils/etiquetas'

/**
 * Selector de ubicación (INV-26 fix, A2.7). Solo se monta cuando el rol lo
 * permite (gerente o admin_bodega); el padre decide con `showSelector`.
 * `incluirBodega={false}` deja solo las sucursales físicas (pronóstico).
 * `opcionVacia` es el texto de la opción sin sucursal: "Elegir sucursal" en
 * Predicciones, donde no hay pronóstico de todas (INV-26, V10).
 */
export default function SucursalSelector({ value, onChange, incluirBodega = true, opcionVacia = 'Todas las sucursales' }) {
  const { sucursales, error } = useSucursales()
  const opciones = incluirBodega ? sucursales : sucursales.filter(s => s.tipo !== BODEGA)

  return (
    <div className="flex items-center gap-2">
      <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
      <select
        aria-label="Sucursal"
        value={value ?? ''}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
        className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden font-medium text-slate-700 cursor-pointer"
      >
        <option value="">{opcionVacia}</option>
        {opciones.map(s => (
          <option key={s.id_sucursal} value={s.id_sucursal}>
            {nombreUbicacion(s)}
          </option>
        ))}
      </select>
      {error && (
        <span role="alert" className="text-xs text-red-600">No se pudieron cargar las sucursales</span>
      )}
    </div>
  )
}
