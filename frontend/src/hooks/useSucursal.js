import { useState } from 'react'
import { useAuth } from '../api/AuthContext'
import { BODEGA } from '../utils/etiquetas'
import { useSucursales } from './useSucursales'

/**
 * Maneja la selección de ubicación según el rol del usuario (INV-26 fix, A2.6).
 *
 * gerente, admin_bodega → eligen todas o una (showSelector = true)
 * admin_sucursal        → fija a su sucursal, la de /auth/me (id_sucursal)
 *
 * Devuelve también el nombre de la ubicación (las recomendaciones de INV-27
 * filtran por nombre) y si es la Bodega Central.
 */
export function useSucursal() {
  const { user } = useAuth()
  const { porId } = useSucursales()
  const [elegida, setElegida] = useState(null) // null = todas

  const showSelector = ['gerente', 'admin_bodega'].includes(user?.rol)
  const esAdminSucursal = user?.rol === 'admin_sucursal'

  const sucursalId = esAdminSucursal ? (user?.id_sucursal ?? null) : elegida
  const sucursalNombre = esAdminSucursal
    ? (user?.sucursal_nombre ?? null)
    : (porId[elegida]?.nombre ?? null)

  return {
    sucursalId,                 // valor que se envía a la API
    rawSucursalId: elegida,     // valor del selector (sin forzar)
    setSucursalId: setElegida,
    showSelector,
    sucursalNombre,
    esBodega: sucursalId !== null && porId[sucursalId]?.tipo === BODEGA,
  }
}
