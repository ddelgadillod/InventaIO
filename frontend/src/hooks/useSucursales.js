import { useEffect, useMemo, useState } from 'react'
import { getSucursales } from '../api/client'
import { BODEGA } from '../utils/etiquetas'

/**
 * Lista de ubicaciones de /consulta/sucursales (INV-26 fix, A2.5). Se pide una
 * sola vez aunque la usen varios componentes; si falla, el siguiente que la
 * use la vuelve a pedir.
 */
let promesa = null

export function cargarSucursales() {
  if (!promesa) {
    promesa = getSucursales()
      .then(data => data.items || [])
      .catch(err => { promesa = null; throw err })
  }
  return promesa
}

// Solo para pruebas: olvida la lista cargada
export function reiniciarSucursales() {
  promesa = null
}

export function useSucursales() {
  const [estado, setEstado] = useState({ sucursales: [], cargando: true, error: null })

  useEffect(() => {
    let vigente = true
    cargarSucursales()
      .then(sucursales => vigente && setEstado({ sucursales, cargando: false, error: null }))
      .catch(error => vigente && setEstado({ sucursales: [], cargando: false, error }))
    return () => { vigente = false }
  }, [])

  const { sucursales } = estado
  const porId = useMemo(() => Object.fromEntries(sucursales.map(s => [s.id_sucursal, s])), [sucursales])
  const porNombre = useMemo(() => Object.fromEntries(sucursales.map(s => [s.nombre, s])), [sucursales])
  const fisicas = useMemo(() => sucursales.filter(s => s.tipo !== BODEGA), [sucursales])

  return { ...estado, porId, porNombre, fisicas }
}
