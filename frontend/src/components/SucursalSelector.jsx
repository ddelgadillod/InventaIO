import { useState, useEffect } from 'react'
import { getSucursales } from '../api/client'
import { Building2 } from 'lucide-react'

/**
 * Selector de sucursal. Solo se monta cuando el rol lo permite
 * (gerente o admin_bodega). El padre decide mostrarlo con `showSelector`.
 */
export default function SucursalSelector({ value, onChange }) {
  const [sucursales, setSucursales] = useState([])

  useEffect(() => {
    getSucursales()
      .then(data => setSucursales(data.items || []))
      .catch(() => {}) // silenciar — el selector queda con solo "Todas"
  }, [])

  return (
    <div className="flex items-center gap-2">
      <Building2 className="w-4 h-4 text-slate-400 flex-shrink-0" />
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
        className="h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-none font-medium text-slate-700 cursor-pointer"
      >
        <option value="">Todas las sucursales</option>
        {sucursales.map(s => (
          <option key={s.id_sucursal} value={s.id_sucursal}>
            {s.nombre}
          </option>
        ))}
      </select>
    </div>
  )
}
