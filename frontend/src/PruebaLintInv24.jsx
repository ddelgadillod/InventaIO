import { useState } from 'react'

// Prueba de verificación de INV-24: un hook dentro de un condicional
export default function PruebaLint({ x }) {
  if (x) {
    const [a] = useState(0)
    return a
  }
  return null
}
