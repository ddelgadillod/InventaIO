import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Consulta a la API desde una página (INV-26 fix, A2.10).
 *
 *   const { datos, cargando, error, recargar } = useConsulta(
 *     op => getInventario(params, op),   // op = { signal, timeoutMs }: pasarlo a client.js
 *     [page, sucursalId],                // se repite la consulta cuando cambian
 *     { timeoutMs, activo },             // activo: false → no consulta
 *   )
 *
 * Cuando cambian las dependencias cancela la consulta anterior, ignora la
 * cancelada y nunca deja en pantalla la respuesta de un filtro anterior.
 */
export function useConsulta(fn, deps, { timeoutMs, activo = true } = {}) {
  const [estado, setEstado] = useState({ datos: null, cargando: activo, error: null })
  const [recargas, setRecargas] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!activo) {
      setEstado({ datos: null, cargando: false, error: null })
      return undefined
    }
    const controller = new AbortController()
    const llamar = fnRef.current // la de este render, con estos filtros
    let vigente = true
    setEstado({ datos: null, cargando: true, error: null })
    new Promise(resolve => resolve(llamar({ signal: controller.signal, timeoutMs })))
      .then(datos => { if (vigente) setEstado({ datos, cargando: false, error: null }) })
      .catch(error => {
        if (vigente && !error?.cancelada) setEstado({ datos: null, cargando: false, error })
      })
    return () => {
      vigente = false
      controller.abort()
    }
  }, [...deps, activo, timeoutMs, recargas]) // fn se lee de fnRef: las dependencias las pone quien llama

  const recargar = useCallback(() => setRecargas(n => n + 1), [])
  return { ...estado, recargar }
}
