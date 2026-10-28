import { useId } from 'react'

// Identidad de Vera v2 (paquete vera-v2): el ícono es una burbuja cerrada con tres
// barras, la alta en teal sale por el borde. Va en línea para poder animar las barras
const BURBUJA = 'M36 28H84A28 28 0 0 1 112 56V76A28 28 0 0 1 84 104H50L20.5 119.6Q13.5 123.2 14.8 115.6L17.2 99.6A28 28 0 0 1 8 76V56A28 28 0 0 1 36 28Z'

const COLORES = {
  // variante: [burbuja o círculo, barra 1, barra 2]; la barra 3 es siempre teal
  icono: ['#1E3A5F', '#93C5FD', '#60A5FA'],
  'icono-oscuro': ['#EFF6FF', '#60A5FA', '#2563EB'],
  avatar: ['#1E3A5F', '#93C5FD', '#60A5FA'],
  'avatar-claro': ['#EFF6FF', '#60A5FA', '#2563EB'],
}
const TEAL = '#14B8A6'

/**
 * variante: 'icono' | 'icono-oscuro' (burbuja) o 'avatar' | 'avatar-claro' (círculo).
 * pensando: las barras suben y bajan (index.css); quietas con "reducir movimiento".
 * Sin `titulo` es decorativo (va junto a un texto o dentro de un botón con nombre): se oculta
 * a los lectores de pantalla en vez de quedar como una imagen sin nombre.
 */
export default function Vera({ variante = 'icono', pensando = false, className = 'w-8 h-8', titulo = 'Vera' }) {
  const idMascara = useId()
  const [fondo, c1, c2] = COLORES[variante] ?? COLORES.icono
  const esAvatar = variante.startsWith('avatar')
  const [x, altas] = esAvatar
    ? [[32, 56, 80], [[66, 18], [52, 32], [30, 54]]]
    : [[28, 52, 76], [[58, 18], [44, 32], [10, 66]]]
  const clase = n => `vera-barra vera-barra-${n}${pensando ? ' vera-pensando' : ''}`
  return (
    <svg viewBox="0 0 128 128" className={className}
      {...(titulo ? { role: 'img', 'aria-label': titulo } : { 'aria-hidden': true })}>
      {esAvatar ? (
        <circle cx="64" cy="64" r="64" fill={fondo} />
      ) : (
        <>
          <defs>
            <mask id={idMascara} maskUnits="userSpaceOnUse" x="0" y="0" width="128" height="128">
              <rect width="128" height="128" fill="#fff" />
              <rect x="70" y="4" width="28" height="78" rx="14" fill="#000" />
            </mask>
          </defs>
          <path d={BURBUJA} fill={fondo} mask={`url(#${idMascara})`} />
        </>
      )}
      {[c1, c2, TEAL].map((color, i) => (
        <rect key={i} className={clase(i + 1)} x={x[i]} y={altas[i][0]} width="16" height={altas[i][1]} rx="8" fill={color} />
      ))}
    </svg>
  )
}
