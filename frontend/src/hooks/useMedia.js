import { useEffect, useState } from 'react'

// ¿La ventana cumple la media query? Sin matchMedia (jsdom) se toma como pantalla ancha
export default function useMedia(consulta) {
  const [cumple, setCumple] = useState(() => window.matchMedia?.(consulta)?.matches ?? true)
  useEffect(() => {
    const mq = window.matchMedia?.(consulta)
    if (!mq) return undefined
    const cambiar = () => setCumple(mq.matches)
    mq.addEventListener('change', cambiar)
    return () => mq.removeEventListener('change', cambiar)
  }, [consulta])
  return cumple
}
