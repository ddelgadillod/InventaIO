import { useState } from 'react'
import { useAuth } from '../api/AuthContext'

/**
 * Maneja la selección de sucursal según el rol del usuario.
 *
 * gerente      → puede elegir todas o una específica (showSelector = true)
 * admin_bodega → puede elegir todas o una específica (showSelector = true)
 * admin_sucursal → fija a su propia sucursal (showSelector = false)
 */
export function useSucursal() {
  const { user } = useAuth()
  const [sucursalId, setSucursalId] = useState(null) // null = todas

  const showSelector = ['gerente', 'admin_bodega'].includes(user?.rol)

  // admin_sucursal siempre ve solo su sucursal — los demás usan el selector
  const efectivaSucursalId =
    user?.rol === 'admin_sucursal' ? user.sucursal_id : sucursalId

  return {
    sucursalId: efectivaSucursalId, // valor que se envía a la API
    rawSucursalId: sucursalId,      // valor del selector (sin forzar)
    setSucursalId,
    showSelector,
  }
}
